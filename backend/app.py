import json
import os
from datetime import date, datetime, timedelta
from io import BytesIO

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
from mysql.connector import Error

from db import bootstrap_database, get_db_connection, hash_password, run_query
from pdf_utils import build_invoice_pdf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.normpath(os.path.join(BASE_DIR, '..', 'frontend'))

app = Flask(__name__)
CORS(app)
bootstrap_database()


def parse_date(value, label):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        raise ValueError(f'Invalid {label}. Use YYYY-MM-DD.')


def get_current_user_id():
    user_id = request.headers.get('X-User-Id')
    return int(user_id) if user_id else None


def require_auth():
    user_id = get_current_user_id()
    if not user_id:
        return None, (jsonify({'message': 'Authentication required.'}), 401)
    return user_id, None


def get_cancellation_policy(check_in_date):
    days_before = (check_in_date - date.today()).days
    if days_before >= 7:
        return 'Free'
    if days_before >= 2:
        return 'Partial'
    return 'No Refund'


def calculate_total_price(price_per_night, check_in_date, check_out_date):
    nights = (check_out_date - check_in_date).days
    if nights <= 0:
        raise ValueError('Check-out must be after check-in.')
    return round(float(price_per_night) * nights, 2)


def validate_booking_dates(check_in_date, check_out_date, blocked_dates):
    if check_in_date < date.today():
        raise ValueError('Check-in cannot be in past.')
    if check_out_date <= check_in_date:
        raise ValueError('Check-out must be after check-in.')

    current = check_in_date
    while current < check_out_date:
        if current.isoformat() in blocked_dates:
            raise ValueError(
                f'Room is not available on {current.strftime("%d %b %Y")}. Please choose different dates.'
            )
        current += timedelta(days=1)


def serialize_modification_history(raw_value):
    if not raw_value:
        return []
    if isinstance(raw_value, list):
        return raw_value
    try:
        return json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        return []


def get_room_snapshot(cursor, room_id):
    cursor.execute(
        '''
        SELECT room_id, room_type, price, location, rating, total_reviews, capacity, amenities,
               max_bookings, floor_level, view_type, image_url, description, features
        FROM ROOM
        WHERE room_id = %s
        ''',
        (room_id,),
    )
    return cursor.fetchone()


def get_booked_dates(cursor, room_id, start_date, days, exclude_booking_id=None):
    end_date = start_date + timedelta(days=days)
    query = '''
        SELECT check_in_date, check_out_date
        FROM BOOKING
        WHERE room_id = %s
          AND booking_status = 'Booked'
          AND check_in_date < %s
          AND check_out_date > %s
    '''
    params = [room_id, end_date, start_date]

    if exclude_booking_id is not None:
        query += ' AND booking_id <> %s'
        params.append(exclude_booking_id)

    cursor.execute(query, tuple(params))
    ranges = cursor.fetchall()
    blocked_dates = set()

    for booking_range in ranges:
        current = max(booking_range['check_in_date'], start_date)
        end = min(booking_range['check_out_date'], end_date)
        while current < end:
            blocked_dates.add(current.isoformat())
            current += timedelta(days=1)

    return blocked_dates


def check_room_availability_atomic(cursor, room_id, check_in_date, check_out_date, exclude_booking_id=None):
    """
    Atomic availability check using the same cursor/connection as the booking transaction.
    This prevents race conditions by checking availability within the locked transaction.
    """
    query = '''
        SELECT COUNT(*) AS count
        FROM BOOKING
        WHERE room_id = %s
          AND booking_status = 'Booked'
          AND check_in_date < %s
          AND check_out_date > %s
    '''
    params = [room_id, check_out_date, check_in_date]

    if exclude_booking_id is not None:
        query += ' AND booking_id <> %s'
        params.append(exclude_booking_id)

    cursor.execute(query, tuple(params))
    conflict = cursor.fetchone()
    return (conflict['count'] if conflict else 0) == 0


def check_room_availability(cursor, room_id, check_in_date, check_out_date, exclude_booking_id=None):
    query = '''
        SELECT COUNT(*) AS count
        FROM BOOKING
        WHERE room_id = %s
          AND booking_status = 'Booked'
          AND check_in_date < %s
          AND check_out_date > %s
    '''
    params = [room_id, check_out_date, check_in_date]

    if exclude_booking_id is not None:
        query += ' AND booking_id <> %s'
        params.append(exclude_booking_id)

    cursor.execute(query, tuple(params))
    conflict = cursor.fetchone()
    return (conflict['count'] if conflict else 0) == 0


def build_modification_entry(booking, room, new_room, new_check_in, new_check_out, new_guests, new_total_price):
    return {
        'changed_at': datetime.now().isoformat(timespec='seconds'),
        'previous': {
            'room_id': booking['room_id'],
            'room_type': room['room_type'],
            'check_in_date': booking['check_in_date'].isoformat(),
            'check_out_date': booking['check_out_date'].isoformat(),
            'guests': booking['guest_count'],
            'total_price': float(booking['total_price']),
        },
        'updated': {
            'room_id': new_room['room_id'],
            'room_type': new_room['room_type'],
            'check_in_date': new_check_in.isoformat(),
            'check_out_date': new_check_out.isoformat(),
            'guests': new_guests,
            'total_price': float(new_total_price),
        },
    }


def build_cancellation_entry(booking, cancellation_policy, refund_amount):
    return {
        'changed_at': datetime.now().isoformat(timespec='seconds'),
        'action': 'cancelled',
        'previous': {
            'booking_status': booking['booking_status'],
            'refund_amount': float(booking.get('refund_amount') or 0),
        },
        'updated': {
            'booking_status': 'Cancelled',
            'cancellation_policy': cancellation_policy,
            'refund_amount': float(refund_amount),
        },
    }


def get_invoice_breakdown(amount):
    subtotal = round(float(amount or 0), 2)
    tax_rate = 0.12
    tax_amount = round(subtotal * tax_rate, 2)
    grand_total = round(subtotal + tax_amount, 2)
    return {
        'subtotal': subtotal,
        'tax_rate': int(tax_rate * 100),
        'tax_amount': tax_amount,
        'grand_total': grand_total,
    }


def refresh_room_rating(cursor, room_id):
    cursor.execute(
        '''
        SELECT ROUND(AVG(rating), 2) AS average_rating, COUNT(*) AS review_count
        FROM REVIEW
        WHERE room_id = %s
        ''',
        (room_id,),
    )
    metrics = cursor.fetchone() or {'average_rating': None, 'review_count': 0}
    cursor.execute(
        '''
        UPDATE ROOM
        SET rating = %s,
            total_reviews = %s
        WHERE room_id = %s
        ''',
        (
            float(metrics['average_rating']) if metrics['average_rating'] is not None else 4.0,
            int(metrics['review_count'] or 0),
            room_id,
        ),
    )
    return {
        'rating': float(metrics['average_rating']) if metrics['average_rating'] is not None else 4.0,
        'total_reviews': int(metrics['review_count'] or 0),
    }


def parse_positive_int(value, default, minimum, maximum):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, minimum), maximum)


def parse_non_negative_float(value, default=None):
    if value in (None, ''):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(parsed, 0.0)


def parse_amenities_param(raw_value):
    if not raw_value:
        return []
    return [token.strip() for token in str(raw_value).split(',') if token.strip()]


def get_room_search_filters(args):
    min_price = parse_non_negative_float(args.get('min_price'), 0.0)
    max_price = parse_non_negative_float(args.get('max_price'))
    if max_price is not None and min_price is not None and min_price > max_price:
        min_price, max_price = max_price, min_price

    return {
        'min_price': min_price,
        'max_price': max_price,
        'location': str(args.get('location', '')).strip(),
        'rating': parse_non_negative_float(args.get('rating')),
        'amenities': parse_amenities_param(args.get('amenities')),
        'page': parse_positive_int(args.get('page'), 1, 1, 1000),
        'page_size': parse_positive_int(args.get('page_size'), 6, 1, 24),
    }


def build_room_search_where(filters):
    clauses = []
    params = []

    if filters['min_price'] is not None:
        clauses.append('R.price >= %s')
        params.append(filters['min_price'])
    if filters['max_price'] is not None:
        clauses.append('R.price <= %s')
        params.append(filters['max_price'])
    if filters['location']:
        clauses.append('R.location = %s')
        params.append(filters['location'])
    if filters['rating'] is not None:
        clauses.append('R.rating >= %s')
        params.append(filters['rating'])
    for amenity in filters['amenities']:
        clauses.append('LOWER(R.amenities) LIKE %s')
        params.append(f'%{amenity.lower()}%')

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    return where_sql, params


def get_room_filter_metadata(cursor):
    cursor.execute('SELECT MIN(price) AS min_price, MAX(price) AS max_price FROM ROOM')
    bounds = cursor.fetchone() or {'min_price': 0, 'max_price': 10000}

    cursor.execute('SELECT DISTINCT location FROM ROOM WHERE location IS NOT NULL AND location <> "" ORDER BY location')
    locations = [row['location'] for row in cursor.fetchall()]

    cursor.execute('SELECT amenities FROM ROOM WHERE amenities IS NOT NULL AND amenities <> ""')
    amenity_tokens = set()
    for row in cursor.fetchall():
        for token in row['amenities'].split(','):
            cleaned = token.strip()
            if cleaned:
                amenity_tokens.add(cleaned)

    return {
        'locations': locations,
        'amenities': sorted(amenity_tokens),
        'price_bounds': {
            'min': float(bounds.get('min_price') or 0),
            'max': float(bounds.get('max_price') or 10000),
        },
        'ratings': [3.0, 3.5, 4.0, 4.5, 4.8],
    }


@app.route('/', methods=['GET'])
def home():
    return send_from_directory(FRONTEND_DIR, 'index.html')


@app.route('/style.css', methods=['GET'])
def styles():
    return send_from_directory(FRONTEND_DIR, 'style.css')


@app.route('/script.js', methods=['GET'])
def scripts():
    return send_from_directory(FRONTEND_DIR, 'script.js')


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    email = str(data.get('email', '')).strip()
    password = str(data.get('password', '')).strip()

    if not email or not password:
        return jsonify({'message': 'Email and password required.'}), 400

    try:
        user = run_query(
            '''
            SELECT user_id, email, full_name, phone, role
            FROM USERS
            WHERE email = %s AND password = %s
            ''',
            (email, hash_password(password)),
            fetchone=True,
        )
        if not user:
            return jsonify({'message': 'Invalid email or password.'}), 401
        return jsonify({'message': 'Login successful!', 'user': user})
    except Error as exc:
        return jsonify({'message': f'Login failed: {exc}'}), 500


@app.route('/signup', methods=['POST'])
def signup():
    data = request.get_json(silent=True) or {}
    name = str(data.get('name', '')).strip()
    phone = str(data.get('phone', '')).strip()
    email = str(data.get('email', '')).strip()
    password = str(data.get('password', '')).strip()

    if not name or not phone or not email or not password:
        return jsonify({'message': 'All fields required.'}), 400
    if len(phone) != 10 or not phone.isdigit():
        return jsonify({'message': 'Valid 10-digit phone required.'}), 400

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute('SELECT user_id FROM USERS WHERE email = %s', (email,))
        if cursor.fetchone():
            return jsonify({'message': 'Email already registered.'}), 409

        cursor.execute(
            '''
            INSERT INTO USERS(email, password, full_name, phone, role)
            VALUES (%s, %s, %s, %s, 'customer')
            ''',
            (email, hash_password(password), name, phone),
        )
        user_id = cursor.lastrowid
        cursor.execute(
            'INSERT INTO CUSTOMER(user_id, name, phone, email) VALUES (%s, %s, %s, %s)',
            (user_id, name, phone, email),
        )
        connection.commit()
        return jsonify({'message': 'Account created successfully! Please login.'})
    except Error as exc:
        if connection:
            connection.rollback()
        return jsonify({'message': f'Signup failed: {exc}'}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route('/rooms', methods=['GET'])
def get_rooms():
    connection = None
    cursor = None
    try:
        filters = get_room_search_filters(request.args)
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        base_query = '''
            FROM ROOM R
            LEFT JOIN (
                SELECT room_id, COUNT(*) AS booking_count
                FROM BOOKING
                WHERE booking_status = 'Booked'
                  AND check_out_date > CURDATE()
                GROUP BY room_id
            ) B ON R.room_id = B.room_id
        '''
        where_sql, params = build_room_search_where(filters)

        cursor.execute(f'SELECT COUNT(*) AS total {base_query} {where_sql}', tuple(params))
        total_items = cursor.fetchone()['total']

        offset = (filters['page'] - 1) * filters['page_size']
        cursor.execute(
            f'''
            SELECT R.*,
                   COALESCE(B.booking_count, 0) AS booking_count,
                   GREATEST(R.max_bookings - COALESCE(B.booking_count, 0), 0) AS available_slots,
                   CASE
                       WHEN GREATEST(R.max_bookings - COALESCE(B.booking_count, 0), 0) > 0 THEN 'Available'
                       ELSE 'Full'
                   END AS status,
                   CASE
                       WHEN GREATEST(R.max_bookings - COALESCE(B.booking_count, 0), 0) > 0 THEN TRUE
                       ELSE FALSE
                   END AS is_available
            {base_query}
            {where_sql}
            ORDER BY R.rating DESC, R.price ASC, R.room_id ASC
            LIMIT %s OFFSET %s
            ''',
            tuple(params + [filters['page_size'], offset]),
        )
        rooms = cursor.fetchall()
        filters_metadata = get_room_filter_metadata(cursor)

        return jsonify(
            {
                'items': rooms,
                'pagination': {
                    'page': filters['page'],
                    'page_size': filters['page_size'],
                    'total_items': total_items,
                    'total_pages': max((total_items + filters['page_size'] - 1) // filters['page_size'], 1),
                },
                'applied_filters': filters,
                'filters': filters_metadata,
            }
        )
    except Error as exc:
        return jsonify({'message': f'Unable to load rooms: {exc}'}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route('/booking-options', methods=['GET'])
def booking_options():
    try:
        rooms = run_query(
            'SELECT room_id, room_type, price, location, rating, total_reviews, capacity, amenities FROM ROOM ORDER BY price, room_id'
        )
        return jsonify(rooms)
    except Error as exc:
        return jsonify({'message': f'Failed to load booking options: {exc}'}), 500


@app.route('/rooms/<int:room_id>/availability', methods=['GET'])
def room_availability(room_id):
    start_param = request.args.get('start')
    days = request.args.get('days', default=45, type=int)
    exclude_booking_id = request.args.get('exclude_booking_id', type=int)
    days = min(max(days or 45, 14), 90)

    try:
        start_date = parse_date(start_param, 'start date') if start_param else date.today()
    except ValueError as exc:
        return jsonify({'message': str(exc)}), 400

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        room = get_room_snapshot(cursor, room_id)
        if not room:
            return jsonify({'message': 'Room not found.'}), 404

        blocked_dates = get_booked_dates(cursor, room_id, start_date, days, exclude_booking_id)
        calendar = []
        for offset in range(days):
            current = start_date + timedelta(days=offset)
            calendar.append(
                {
                    'date': current.isoformat(),
                    'day': current.day,
                    'weekday': current.strftime('%a'),
                    'is_past': current < date.today(),
                    'is_blocked': current.isoformat() in blocked_dates,
                }
            )

        return jsonify(
            {
                'room_id': room_id,
                'room_type': room['room_type'],
                'calendar': calendar,
                'blocked_dates': sorted(blocked_dates),
            }
        )
    except Error as exc:
        return jsonify({'message': f'Failed to load availability: {exc}'}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route('/rooms/<int:room_id>/reviews', methods=['GET'])
def room_reviews(room_id):
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        room = get_room_snapshot(cursor, room_id)
        if not room:
            return jsonify({'message': 'Room not found.'}), 404

        cursor.execute(
            '''
            SELECT
                RV.review_id,
                RV.booking_id,
                RV.rating,
                RV.review_text,
                RV.created_at,
                U.full_name
            FROM REVIEW RV
            JOIN USERS U ON U.user_id = RV.user_id
            WHERE RV.room_id = %s
            ORDER BY RV.created_at DESC
            LIMIT 8
            ''',
            (room_id,),
        )
        reviews = cursor.fetchall()
        return jsonify(
            {
                'room_id': room_id,
                'rating': float(room.get('rating') or 0),
                'total_reviews': int(room.get('total_reviews') or 0),
                'reviews': reviews,
            }
        )
    except Error as exc:
        return jsonify({'message': f'Failed to load reviews: {exc}'}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route('/book', methods=['POST'])
def book_room():
    user_id, error = require_auth()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    room_id = data.get('room_id')
    check_in = data.get('check_in')
    check_out = data.get('check_out')
    guests = int(data.get('guests', 1) or 1)

    if not room_id or not check_in or not check_out:
        return jsonify({'message': 'Room and dates required.'}), 400

    try:
        check_in_date = parse_date(check_in, 'check-in date')
        check_out_date = parse_date(check_out, 'check-out date')
    except ValueError as exc:
        return jsonify({'message': str(exc)}), 400

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Start transaction
        connection.start_transaction()

        # STEP 1: Lock the room for update to prevent concurrent bookings
        cursor.execute('SELECT * FROM ROOM WHERE room_id = %s FOR UPDATE', (room_id,))
        room = cursor.fetchone()

        if not room:
            connection.rollback()
            return jsonify({'message': 'Room not found.'}), 404

        if guests > room['capacity']:
            connection.rollback()
            return jsonify({'message': 'Selected room cannot accommodate that many guests.'}), 400

        # STEP 2: Check availability with locked room (prevents race conditions)
        if not check_room_availability_atomic(cursor, room_id, check_in_date, check_out_date):
            connection.rollback()
            return jsonify({'message': 'Room unavailable for these dates.'}), 409

        # STEP 3: Calculate total price
        total_price = calculate_total_price(room['price'], check_in_date, check_out_date)

        # STEP 4: Create booking atomically
        cursor.execute(
            '''
            INSERT INTO BOOKING(
                user_id, room_id, check_in_date, check_out_date, booking_date, status,
                booking_status, guest_count, cancellation_policy, refund_amount,
                modification_history, total_price, payment_status
            )
            VALUES (%s, %s, %s, %s, NOW(), 'Confirmed', 'Booked', %s, %s, 0, %s, %s, 'Completed')
            ''',
            (
                user_id,
                room_id,
                check_in_date,
                check_out_date,
                guests,
                get_cancellation_policy(check_in_date),
                json.dumps([]),
                total_price,
            ),
        )

        booking_id = cursor.lastrowid

        # STEP 5: Verify booking was created successfully
        cursor.execute('SELECT booking_id FROM BOOKING WHERE booking_id = %s', (booking_id,))
        if not cursor.fetchone():
            connection.rollback()
            return jsonify({'message': 'Failed to create booking.'}), 500

        # STEP 6: Commit transaction (all steps successful)
        connection.commit()

        return jsonify({
            'message': 'Booking successful!',
            'booking_id': booking_id,
            'total_price': total_price
        })

    except Error as exc:
        # Rollback on any database error
        if connection:
            try:
                connection.rollback()
            except:
                pass  # Ignore rollback errors
        return jsonify({'message': f'Booking failed: {exc}'}), 500

    except Exception as exc:
        # Rollback on any unexpected error
        if connection:
            try:
                connection.rollback()
            except:
                pass  # Ignore rollback errors
        return jsonify({'message': f'Unexpected error: {exc}'}), 500

    finally:
        # Always close cursor and connection
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if connection:
            try:
                connection.close()
            except:
                pass


@app.route('/modify/<int:booking_id>', methods=['POST'])
def modify_booking(booking_id):
    user_id, error = require_auth()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    new_room_id = data.get('room_id')
    new_check_in = data.get('check_in')
    new_check_out = data.get('check_out')
    new_guests = int(data.get('guests', 1) or 1)

    if not new_room_id or not new_check_in or not new_check_out:
        return jsonify({'message': 'Room and dates required for modification.'}), 400

    try:
        new_check_in_date = parse_date(new_check_in, 'check-in date')
        new_check_out_date = parse_date(new_check_out, 'check-out date')
    except ValueError as exc:
        return jsonify({'message': str(exc)}), 400

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Start transaction
        connection.start_transaction()

        # STEP 1: Lock the booking for update
        cursor.execute(
            '''
            SELECT B.*, R.room_type, R.capacity, R.price
            FROM BOOKING B
            JOIN ROOM R ON B.room_id = R.room_id
            WHERE B.booking_id = %s AND B.user_id = %s
            FOR UPDATE
            ''',
            (booking_id, user_id),
        )
        booking = cursor.fetchone()

        if not booking:
            connection.rollback()
            return jsonify({'message': 'Booking not found.'}), 404

        if booking['booking_status'] == 'Cancelled':
            connection.rollback()
            return jsonify({'message': 'Cannot modify cancelled booking.'}), 400

        if booking['check_in_date'] <= date.today():
            connection.rollback()
            return jsonify({'message': 'Cannot modify past or ongoing bookings.'}), 400

        # STEP 2: Lock the new room if different
        if new_room_id != booking['room_id']:
            cursor.execute('SELECT * FROM ROOM WHERE room_id = %s FOR UPDATE', (new_room_id,))
            new_room = cursor.fetchone()
            if not new_room:
                connection.rollback()
                return jsonify({'message': 'New room not found.'}), 404
            if new_guests > new_room['capacity']:
                connection.rollback()
                return jsonify({'message': 'New room cannot accommodate that many guests.'}), 400
            room_price = new_room['price']
        else:
            new_room = {'room_type': booking['room_type'], 'capacity': booking['capacity']}
            room_price = booking['price']

        # STEP 3: Check availability for new dates/room
        if not check_room_availability_atomic(cursor, new_room_id, new_check_in_date, new_check_out_date, booking_id):
            connection.rollback()
            return jsonify({'message': 'Room unavailable for new dates.'}), 409

        # STEP 4: Calculate new total price
        new_total_price = calculate_total_price(room_price, new_check_in_date, new_check_out_date)

        # STEP 5: Update booking atomically
        history = serialize_modification_history(booking.get('modification_history'))
        history.append(build_modification_entry(booking, new_room, new_room_id, new_check_in_date, new_check_out_date, new_guests, new_total_price))

        cursor.execute(
            '''
            UPDATE BOOKING
            SET room_id = %s,
                check_in_date = %s,
                check_out_date = %s,
                guest_count = %s,
                total_price = %s,
                modification_history = %s
            WHERE booking_id = %s
            ''',
            (
                new_room_id,
                new_check_in_date,
                new_check_out_date,
                new_guests,
                new_total_price,
                json.dumps(history),
                booking_id,
            ),
        )

        # STEP 6: Log modification in history
        cursor.execute(
            '''
            INSERT INTO BOOKING_HISTORY(booking_id, user_id, action_type, previous_data, new_data, note)
            VALUES (%s, %s, 'modified', %s, %s, %s)
            ''',
            (
                booking_id,
                user_id,
                json.dumps({
                    'room_id': booking['room_id'],
                    'check_in_date': str(booking['check_in_date']),
                    'check_out_date': str(booking['check_out_date']),
                    'guest_count': booking['guest_count'],
                    'total_price': float(booking['total_price'])
                }),
                json.dumps({
                    'room_id': new_room_id,
                    'check_in_date': str(new_check_in_date),
                    'check_out_date': str(new_check_out_date),
                    'guest_count': new_guests,
                    'total_price': float(new_total_price)
                }),
                f'Booking modified by user {user_id}',
            ),
        )

        # STEP 7: Commit transaction
        connection.commit()

        return jsonify({
            'message': 'Booking modified successfully!',
            'booking_id': booking_id,
            'new_total_price': new_total_price,
            'price_difference': new_total_price - booking['total_price']
        })

    except Error as exc:
        # Rollback on any database error
        if connection:
            try:
                connection.rollback()
            except:
                pass  # Ignore rollback errors
        return jsonify({'message': f'Modification failed: {exc}'}), 500

    except Exception as exc:
        # Rollback on any unexpected error
        if connection:
            try:
                connection.rollback()
            except:
                pass  # Ignore rollback errors
        return jsonify({'message': f'Unexpected error: {exc}'}), 500

    finally:
        # Always close cursor and connection
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if connection:
            try:
                connection.close()
            except:
                pass


@app.route('/booking-history/<int:booking_id>', methods=['GET'])
def get_booking_history(booking_id):
    user_id, error = require_auth()
    if error:
        return error

    try:
        # Verify user owns this booking
        booking_check = run_query(
            "SELECT booking_id FROM BOOKING WHERE booking_id = %s AND user_id = %s",
            (booking_id, user_id),
            fetchone=True
        )

        if not booking_check:
            return jsonify({'message': 'Booking not found or access denied.'}), 404

        # Get history with user information
        history = run_query(
            """
            SELECT
                h.history_id,
                h.action_type,
                h.previous_data,
                h.new_data,
                h.note,
                h.created_at,
                u.full_name as user_name,
                u.email as user_email
            FROM BOOKING_HISTORY h
            JOIN USERS u ON h.user_id = u.user_id
            WHERE h.booking_id = %s
            ORDER BY h.created_at DESC
            """,
            (booking_id,)
        )

        return jsonify(history or [])

    except Error as exc:
        return jsonify({'message': f'Failed to retrieve booking history: {exc}'}), 500


@app.route('/my-bookings', methods=['GET'])
def get_my_bookings():
    user_id, error = require_auth()
    if error:
        return error

    try:
        bookings = run_query(
            '''
            SELECT
                B.booking_id,
                B.room_id,
                R.room_type,
                R.capacity,
                B.check_in_date,
                B.check_out_date,
                B.status,
                B.booking_status,
                B.guest_count AS guests,
                B.cancellation_policy,
                B.refund_amount,
                B.modification_history,
                B.total_price,
                B.payment_status,
                B.booking_date,
                RV.review_id,
                RV.rating AS review_rating,
                RV.review_text,
                RV.created_at AS review_created_at
            FROM BOOKING B
            JOIN ROOM R ON R.room_id = B.room_id
            LEFT JOIN REVIEW RV ON RV.booking_id = B.booking_id
            WHERE B.user_id = %s
            ORDER BY B.check_in_date DESC
            ''',
            (user_id,),
        )
        for booking in bookings:
            booking['modification_history'] = serialize_modification_history(booking.get('modification_history'))
            booking['has_review'] = bool(booking.get('review_id'))
        return jsonify(bookings)
    except Error as exc:
        return jsonify({'message': f'Failed to load bookings: {exc}'}), 500


@app.route('/booking/<int:booking_id>/invoice', methods=['GET'])
def download_booking_invoice(booking_id):
    user_id, error = require_auth()
    if error:
        return error

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            '''
            SELECT
                B.booking_id,
                B.check_in_date,
                B.check_out_date,
                B.booking_date,
                B.guest_count,
                B.total_price,
                B.booking_status,
                U.full_name,
                U.email,
                U.phone,
                R.room_type,
                R.amenities
            FROM BOOKING B
            JOIN USERS U ON U.user_id = B.user_id
            JOIN ROOM R ON R.room_id = B.room_id
            WHERE B.booking_id = %s AND B.user_id = %s
            ''',
            (booking_id, user_id),
        )
        booking = cursor.fetchone()
        if not booking:
            return jsonify({'message': 'Booking not found.'}), 404

        pricing = get_invoice_breakdown(booking['total_price'])
        lines = [
            'Hotel Booking Invoice',
            '',
            f'Invoice For: {booking["full_name"]}',
            f'Email: {booking["email"]}',
            f'Phone: {booking["phone"]}',
            '',
            f'Booking ID: #{booking["booking_id"]}',
            f'Booking Date: {booking["booking_date"].strftime("%d %b %Y %I:%M %p")}',
            f'Status: {booking["booking_status"]}',
            '',
            f'Room Type: {booking["room_type"]}',
            f'Guests: {booking["guest_count"]}',
            f'Check-in: {booking["check_in_date"].strftime("%d %b %Y")}',
            f'Check-out: {booking["check_out_date"].strftime("%d %b %Y")}',
            f'Amenities: {booking["amenities"] or "Standard"}',
            '',
            f'Room Charges: Rs{pricing["subtotal"]:.2f}',
            f'Taxes ({pricing["tax_rate"]}%): Rs{pricing["tax_amount"]:.2f}',
            f'Grand Total: Rs{pricing["grand_total"]:.2f}',
        ]
        pdf_bytes = build_invoice_pdf(lines)
        return send_file(
            BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'booking-invoice-{booking_id}.pdf',
        )
    except Error as exc:
        return jsonify({'message': f'Failed to generate invoice: {exc}'}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route('/booking/<int:booking_id>/review', methods=['POST'])
def submit_review(booking_id):
    user_id, error = require_auth()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    rating = data.get('rating')
    review_text = str(data.get('review_text', '')).strip()

    try:
        rating = int(rating)
    except (TypeError, ValueError):
        return jsonify({'message': 'Rating must be a number between 1 and 5.'}), 400

    if rating < 1 or rating > 5:
        return jsonify({'message': 'Rating must be between 1 and 5.'}), 400
    if len(review_text) > 1200:
        return jsonify({'message': 'Review is too long. Keep it under 1200 characters.'}), 400

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            '''
            SELECT B.booking_id, B.user_id, B.room_id, B.check_out_date, B.booking_status, R.room_type
            FROM BOOKING B
            JOIN ROOM R ON R.room_id = B.room_id
            WHERE B.booking_id = %s AND B.user_id = %s
            ''',
            (booking_id, user_id),
        )
        booking = cursor.fetchone()
        if not booking:
            return jsonify({'message': 'Booking not found.'}), 404
        if booking['booking_status'] == 'Cancelled':
            return jsonify({'message': 'Cancelled bookings cannot be reviewed.'}), 400
        if booking['check_out_date'] >= date.today():
            return jsonify({'message': 'You can review a stay only after check-out.'}), 400

        cursor.execute('SELECT review_id FROM REVIEW WHERE booking_id = %s', (booking_id,))
        if cursor.fetchone():
            return jsonify({'message': 'You have already reviewed this booking.'}), 409

        cursor.execute(
            '''
            INSERT INTO REVIEW(booking_id, user_id, room_id, rating, review_text)
            VALUES (%s, %s, %s, %s, %s)
            ''',
            (booking_id, user_id, booking['room_id'], rating, review_text or None),
        )
        review_id = cursor.lastrowid
        metrics = refresh_room_rating(cursor, booking['room_id'])
        connection.commit()
        return jsonify(
            {
                'message': f'Thanks for reviewing your {booking["room_type"]} stay.',
                'review_id': review_id,
                'rating': rating,
                'review_text': review_text,
                'room_rating': metrics['rating'],
                'total_reviews': metrics['total_reviews'],
            }
        )
    except Error as exc:
        if connection:
            connection.rollback()
        return jsonify({'message': f'Failed to save review: {exc}'}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route('/booking/<int:booking_id>/update', methods=['POST'])
def update_booking(booking_id):
    user_id, error = require_auth()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    room_id = data.get('room_id')
    check_in = data.get('check_in')
    check_out = data.get('check_out')
    guests = int(data.get('guests', 1) or 1)

    if not room_id or not check_in or not check_out:
        return jsonify({'message': 'Room, dates, and guest count are required.'}), 400

    try:
        room_id = int(room_id)
        check_in_date = parse_date(check_in, 'check-in date')
        check_out_date = parse_date(check_out, 'check-out date')
    except ValueError as exc:
        return jsonify({'message': str(exc)}), 400

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            '''
            SELECT booking_id, room_id, check_in_date, check_out_date, guest_count,
                   total_price, booking_status, modification_history
            FROM BOOKING
            WHERE booking_id = %s AND user_id = %s
            ''',
            (booking_id, user_id),
        )
        booking = cursor.fetchone()
        if not booking:
            return jsonify({'message': 'Booking not found.'}), 404
        if booking['booking_status'] != 'Booked':
            return jsonify({'message': 'Only active bookings can be updated.'}), 400

        room = get_room_snapshot(cursor, booking['room_id'])
        new_room = get_room_snapshot(cursor, room_id)
        if not new_room:
            return jsonify({'message': 'Selected room not found.'}), 404
        if guests > new_room['capacity']:
            return jsonify({'message': 'Selected room cannot accommodate that many guests.'}), 400
        blocked_dates = get_booked_dates(cursor, room_id, date.today(), 180, exclude_booking_id=booking_id)
        try:
            validate_booking_dates(check_in_date, check_out_date, blocked_dates)
        except ValueError as exc:
            return jsonify({'message': str(exc)}), 400
        if not check_room_availability(cursor, room_id, check_in_date, check_out_date, exclude_booking_id=booking_id):
            return jsonify({'message': 'Selected room is unavailable for those dates because of an overlapping booking.'}), 409

        total_price = calculate_total_price(new_room['price'], check_in_date, check_out_date)
        history = serialize_modification_history(booking.get('modification_history'))
        history.append(
            build_modification_entry(
                booking,
                room,
                new_room,
                check_in_date,
                check_out_date,
                guests,
                total_price,
            )
        )

        cursor.execute(
            '''
            UPDATE BOOKING
            SET room_id = %s,
                check_in_date = %s,
                check_out_date = %s,
                guest_count = %s,
                total_price = %s,
                cancellation_policy = %s,
                modification_history = %s
            WHERE booking_id = %s AND user_id = %s
            ''',
            (
                room_id,
                check_in_date,
                check_out_date,
                guests,
                total_price,
                get_cancellation_policy(check_in_date),
                json.dumps(history),
                booking_id,
                user_id,
            ),
        )
        cursor.execute(
            '''
            INSERT INTO BOOKING_HISTORY(booking_id, user_id, action_type, previous_data, new_data, note)
            VALUES (%s, %s, 'modified', %s, %s, %s)
            ''',
            (
                booking_id,
                user_id,
                json.dumps(history[-1]['previous']),
                json.dumps(history[-1]['updated']),
                'Booking updated by customer',
            ),
        )
        connection.commit()
        return jsonify(
            {
                'message': 'Booking updated successfully!',
                'booking_id': booking_id,
                'total_price': total_price,
                'modification_history': history,
            }
        )
    except Error as exc:
        if connection:
            connection.rollback()
        return jsonify({'message': f'Update failed: {exc}'}), 500
    except ValueError as exc:
        if connection:
            connection.rollback()
        return jsonify({'message': str(exc)}), 400
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route('/cancel/<int:booking_id>', methods=['POST'])
def cancel_booking(booking_id):
    user_id, error = require_auth()
    if error:
        return error

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Start transaction
        connection.start_transaction()

        # STEP 1: Lock the booking for update to prevent concurrent operations
        cursor.execute(
            '''
            SELECT booking_id, status, booking_status, check_in_date, total_price, refund_amount, modification_history
            FROM BOOKING
            WHERE booking_id = %s AND user_id = %s
            FOR UPDATE
            ''',
            (booking_id, user_id),
        )
        booking = cursor.fetchone()

        if not booking:
            connection.rollback()
            return jsonify({'message': 'Booking not found.'}), 404

        if booking['booking_status'] == 'Cancelled' or booking['status'] == 'Cancelled':
            connection.rollback()
            return jsonify({'message': 'Already cancelled.'}), 400

        if booking['check_in_date'] <= date.today():
            connection.rollback()
            return jsonify({'message': 'Cannot cancel past bookings.'}), 400

        # STEP 2: Calculate refund based on cancellation policy
        refund_amount = 0
        cancellation_policy = get_cancellation_policy(booking['check_in_date'])
        if cancellation_policy == 'Free':
            refund_amount = float(booking['total_price'])
        elif cancellation_policy == 'Partial':
            refund_amount = float(booking['total_price']) * 0.5

        # STEP 3: Update booking status atomically
        history = serialize_modification_history(booking.get('modification_history'))
        history.append(build_cancellation_entry(booking, cancellation_policy, refund_amount))

        cursor.execute(
            '''
            UPDATE BOOKING
            SET status = 'Cancelled',
                booking_status = 'Cancelled',
                cancellation_policy = %s,
                refund_amount = %s,
                payment_status = %s,
                modification_history = %s
            WHERE booking_id = %s
            ''',
            (
                cancellation_policy,
                refund_amount,
                'Refunded' if refund_amount > 0 else 'No Refund',
                json.dumps(history),
                booking_id,
            ),
        )

        # STEP 4: Verify update was successful
        cursor.execute(
            'SELECT booking_status FROM BOOKING WHERE booking_id = %s',
            (booking_id,)
        )
        updated_booking = cursor.fetchone()
        if not updated_booking or updated_booking['booking_status'] != 'Cancelled':
            connection.rollback()
            return jsonify({'message': 'Failed to cancel booking.'}), 500

        # STEP 5: Log cancellation in history
        cursor.execute(
            '''
            INSERT INTO BOOKING_HISTORY(booking_id, user_id, action_type, previous_data, new_data, note)
            VALUES (%s, %s, 'cancelled', %s, %s, %s)
            ''',
            (
                booking_id,
                user_id,
                json.dumps({'booking_status': booking['booking_status'], 'refund_amount': float(booking.get('refund_amount') or 0)}),
                json.dumps({'booking_status': 'Cancelled', 'refund_amount': float(refund_amount), 'cancellation_policy': cancellation_policy}),
                f'Booking cancelled with {cancellation_policy} policy',
            ),
        )

        # STEP 6: Commit transaction
        connection.commit()

        return jsonify(
            {
                'message': 'Booking cancelled successfully!',
                'booking_status': 'Cancelled',
                'cancellation_policy': cancellation_policy,
                'refund_amount': round(refund_amount, 2),
            }
        )

    except Error as exc:
        # Rollback on any database error
        if connection:
            try:
                connection.rollback()
            except:
                pass  # Ignore rollback errors
        return jsonify({'message': f'Cancellation failed: {exc}'}), 500

    except Exception as exc:
        # Rollback on any unexpected error
        if connection:
            try:
                connection.rollback()
            except:
                pass  # Ignore rollback errors
        return jsonify({'message': f'Unexpected error: {exc}'}), 500

    finally:
        # Always close cursor and connection
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if connection:
            try:
                connection.close()
            except:
                pass


@app.route('/admin/analytics', methods=['GET'])
def admin_analytics():
    user_role = request.headers.get('X-User-Role')
    if user_role != 'admin':
        return jsonify({'message': 'Admin access required.'}), 403

    try:
        # Basic metrics
        revenue = run_query("SELECT COALESCE(SUM(total_price), 0) as total FROM BOOKING WHERE booking_status = 'Booked'", fetchone=True)
        bookings = run_query("SELECT COUNT(*) as count FROM BOOKING WHERE booking_status = 'Booked'", fetchone=True)
        customers = run_query("SELECT COUNT(*) as count FROM USERS WHERE role = 'customer'", fetchone=True)
        max_bookings = run_query('SELECT COALESCE(SUM(max_bookings), 1) as total FROM ROOM', fetchone=True)
        occupancy = int((bookings['count'] / max_bookings['total'] * 100)) if max_bookings and max_bookings['total'] else 0

        # Most booked rooms
        most_booked_rooms = run_query("""
            SELECT R.room_type, COUNT(B.booking_id) as booking_count,
                   SUM(B.total_price) as total_revenue
            FROM ROOM R
            LEFT JOIN BOOKING B ON R.room_id = B.room_id AND B.booking_status = 'Booked'
            GROUP BY R.room_id, R.room_type
            ORDER BY booking_count DESC
            LIMIT 5
        """)

        # Bookings per month (last 12 months)
        monthly_bookings = run_query("""
            SELECT DATE_FORMAT(booking_date, '%Y-%m') as month,
                   COUNT(*) as bookings,
                   SUM(total_price) as revenue
            FROM BOOKING
            WHERE booking_status = 'Booked'
            AND booking_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
            GROUP BY DATE_FORMAT(booking_date, '%Y-%m')
            ORDER BY month DESC
        """)

        # Bookings per day (last 30 days)
        daily_bookings = run_query("""
            SELECT DATE(booking_date) as date,
                   COUNT(*) as bookings,
                   SUM(total_price) as revenue
            FROM BOOKING
            WHERE booking_status = 'Booked'
            AND booking_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            GROUP BY DATE(booking_date)
            ORDER BY date DESC
        """)

        # Revenue by room type
        revenue_by_room = run_query("""
            SELECT R.room_type,
                   COUNT(B.booking_id) as bookings,
                   SUM(B.total_price) as revenue
            FROM ROOM R
            LEFT JOIN BOOKING B ON R.room_id = B.room_id AND B.booking_status = 'Booked'
            GROUP BY R.room_id, R.room_type
            ORDER BY revenue DESC
        """)

        # Cancellation rate
        total_bookings_all = run_query("SELECT COUNT(*) as count FROM BOOKING", fetchone=True)
        cancelled_bookings = run_query("SELECT COUNT(*) as count FROM BOOKING WHERE booking_status = 'Cancelled'", fetchone=True)
        cancellation_rate = (cancelled_bookings['count'] / total_bookings_all['count'] * 100) if total_bookings_all['count'] > 0 else 0

        return jsonify({
            'summary': {
                'total_revenue': int(revenue['total']) if revenue else 0,
                'total_bookings': bookings['count'] if bookings else 0,
                'total_customers': customers['count'] if customers else 0,
                'occupancy_rate': min(occupancy, 100),
                'cancellation_rate': round(cancellation_rate, 1)
            },
            'most_booked_rooms': most_booked_rooms or [],
            'monthly_bookings': monthly_bookings or [],
            'daily_bookings': daily_bookings or [],
            'revenue_by_room': revenue_by_room or []
        })
    except Error as exc:
        return jsonify({'message': f'Failed to load analytics: {exc}'}), 500


@app.route('/admin/bookings', methods=['GET'])
def admin_bookings():
    user_role = request.headers.get('X-User-Role')
    if user_role != 'admin':
        return jsonify({'message': 'Admin access required.'}), 403

    search = request.args.get('search', '').strip()
    status = request.args.get('status', '').strip()
    query = '''
        SELECT B.booking_id, B.check_in_date, B.check_out_date, B.booking_status AS status,
               B.total_price, B.payment_status, R.room_type,
               U.full_name AS customer_name, U.phone AS customer_phone, U.email AS customer_email
        FROM BOOKING B
        JOIN ROOM R ON B.room_id = R.room_id
        JOIN USERS U ON B.user_id = U.user_id
        WHERE 1 = 1
    '''
    params = []
    if search:
        query += ' AND (U.full_name LIKE %s OR U.phone LIKE %s OR U.email LIKE %s)'
        token = f'%{search}%'
        params.extend([token, token, token])
    if status:
        query += ' AND B.booking_status = %s'
        params.append(status)
    query += ' ORDER BY B.check_in_date DESC'

    try:
        return jsonify(run_query(query, tuple(params)))
    except Error as exc:
        return jsonify({'message': f'Failed to load bookings: {exc}'}), 500


@app.route('/admin/customers', methods=['GET'])
def admin_customers():
    user_role = request.headers.get('X-User-Role')
    if user_role != 'admin':
        return jsonify({'message': 'Admin access required.'}), 403

    search = request.args.get('search', '').strip()
    query = '''
        SELECT U.user_id, U.email, U.full_name, U.phone, U.created_at,
               COUNT(B.booking_id) AS booking_count,
               COALESCE(SUM(B.total_price), 0) AS total_spent
        FROM USERS U
        LEFT JOIN BOOKING B ON U.user_id = B.user_id AND B.booking_status = 'Booked'
        WHERE U.role = 'customer'
    '''
    params = []
    if search:
        query += ' AND (U.full_name LIKE %s OR U.phone LIKE %s OR U.email LIKE %s)'
        token = f'%{search}%'
        params.extend([token, token, token])
    query += ' GROUP BY U.user_id ORDER BY U.created_at DESC'
    try:
        return jsonify(run_query(query, tuple(params)))
    except Error as exc:
        return jsonify({'message': f'Failed to load customers: {exc}'}), 500


@app.route('/admin/rooms', methods=['GET'])
def admin_rooms():
    user_role = request.headers.get('X-User-Role')
    if user_role != 'admin':
        return jsonify({'message': 'Admin access required.'}), 403

    try:
        rooms = run_query(
            '''
            SELECT R.room_id, R.room_type, R.price, R.location, R.rating, R.capacity, R.amenities, R.max_bookings,
                   COUNT(B.booking_id) AS booking_count
            FROM ROOM R
            LEFT JOIN BOOKING B ON R.room_id = B.room_id AND B.booking_status = 'Booked' AND B.check_out_date > CURDATE()
            GROUP BY R.room_id
            ORDER BY R.room_id
            '''
        )
        return jsonify(rooms)
    except Error as exc:
        return jsonify({'message': f'Failed to load rooms: {exc}'}), 500


@app.route('/wishlist', methods=['GET'])
def get_wishlist():
    user_id, error = require_auth()
    if error:
        return error

    try:
        wishlist_items = run_query(
            '''
            SELECT W.wishlist_id, W.added_at, R.room_id, R.room_type, R.price, R.location, R.rating,
                   R.capacity, R.amenities, R.max_bookings, R.floor_level, R.view_type, R.image_url,
                   R.description, R.features
            FROM WISHLIST W
            JOIN ROOM R ON W.room_id = R.room_id
            WHERE W.user_id = %s
            ORDER BY W.added_at DESC
            ''',
            (user_id,)
        )
        return jsonify(wishlist_items)
    except Error as exc:
        return jsonify({'message': f'Failed to load wishlist: {exc}'}), 500


@app.route('/wishlist/<int:room_id>', methods=['POST'])
def add_to_wishlist(room_id):
    user_id, error = require_auth()
    if error:
        return error

    try:
        # Check if room exists
        room = run_query('SELECT room_id FROM ROOM WHERE room_id = %s', (room_id,), fetchone=True)
        if not room:
            return jsonify({'message': 'Room not found.'}), 404

        # Add to wishlist (will fail if already exists due to UNIQUE constraint)
        connection = get_db_connection()
        cursor = connection.cursor()
        try:
            cursor.execute(
                'INSERT INTO WISHLIST (user_id, room_id) VALUES (%s, %s)',
                (user_id, room_id)
            )
            connection.commit()
            return jsonify({'message': 'Room added to wishlist successfully.'}), 201
        except Error as exc:
            connection.rollback()
            if 'Duplicate entry' in str(exc):
                return jsonify({'message': 'Room is already in your wishlist.'}), 409
            raise
        finally:
            cursor.close()
            connection.close()
    except Error as exc:
        return jsonify({'message': f'Failed to add room to wishlist: {exc}'}), 500


@app.route('/wishlist/<int:room_id>', methods=['DELETE'])
def remove_from_wishlist(room_id):
    user_id, error = require_auth()
    if error:
        return error

    try:
        # Remove from wishlist
        connection = get_db_connection()
        cursor = connection.cursor()
        try:
            cursor.execute(
                'DELETE FROM WISHLIST WHERE user_id = %s AND room_id = %s',
                (user_id, room_id)
            )
            if cursor.rowcount == 0:
                return jsonify({'message': 'Room not found in your wishlist.'}), 404
            connection.commit()
            return jsonify({'message': 'Room removed from wishlist successfully.'})
        except Error as exc:
            connection.rollback()
            raise
        finally:
            cursor.close()
            connection.close()
    except Error as exc:
        return jsonify({'message': f'Failed to remove room from wishlist: {exc}'}), 500


@app.route('/wishlist/<int:room_id>/status', methods=['GET'])
def check_wishlist_status(room_id):
    user_id, error = require_auth()
    if error:
        return error

    try:
        result = run_query(
            'SELECT wishlist_id FROM WISHLIST WHERE user_id = %s AND room_id = %s',
            (user_id, room_id)
        )
        return jsonify({'in_wishlist': len(result) > 0})
    except Error as exc:
        return jsonify({'message': f'Failed to check wishlist status: {exc}'}), 500


if __name__ == '__main__':
    app.run(debug=True)
