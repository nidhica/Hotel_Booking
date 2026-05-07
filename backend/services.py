import json
from datetime import date, datetime, timedelta

from db import get_db_connection, run_query

TAX_RATE = 0.12


def parse_date(value, field_name):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValueError(f"Invalid {field_name}. Use YYYY-MM-DD format.")


def format_currency(value):
    return round(float(value or 0), 2)


def get_nights(check_in_date, check_out_date):
    nights = (check_out_date - check_in_date).days
    if nights <= 0:
        raise ValueError("Check-out must be after check-in.")
    return nights


def calculate_pricing(room_price, check_in_date, check_out_date):
    nights = get_nights(check_in_date, check_out_date)
    subtotal = round(float(room_price) * nights, 2)
    tax_amount = round(subtotal * TAX_RATE, 2)
    total = round(subtotal + tax_amount, 2)
    return {
        "nights": nights,
        "subtotal": subtotal,
        "tax_amount": tax_amount,
        "total": total,
    }


def get_cancellation_policy(check_in_date):
    days_before = (check_in_date - date.today()).days
    if days_before >= 7:
        return {"label": "Free Cancellation", "refund_ratio": 1.0}
    if days_before >= 2:
        return {"label": "Partial Refund", "refund_ratio": 0.5}
    return {"label": "No Refund", "refund_ratio": 0.0}


def calculate_refund(total_price, check_in_date):
    policy = get_cancellation_policy(check_in_date)
    refund = round(float(total_price or 0) * policy["refund_ratio"], 2)
    return {"policy": policy["label"], "refund_amount": refund}


def ensure_customer_profile(cursor, user_id, full_name, phone, email):
    cursor.execute("SELECT cust_id FROM CUSTOMER WHERE user_id = %s", (user_id,))
    existing = cursor.fetchone()
    if existing:
        cursor.execute(
            """
            UPDATE CUSTOMER
            SET name = %s, phone = %s, email = %s
            WHERE user_id = %s
            """,
            (full_name, phone, email, user_id),
        )
        return existing["cust_id"]

    cursor.execute(
        """
        INSERT INTO CUSTOMER (user_id, name, phone, email)
        VALUES (%s, %s, %s, %s)
        """,
        (user_id, full_name, phone, email),
    )
    return cursor.lastrowid


def count_conflicting_bookings(cursor, room_id, check_in_date, check_out_date, exclude_booking_id=None):
    query = """
        SELECT COUNT(*) AS active_count
        FROM BOOKING
        WHERE room_id = %s
          AND booking_status = 'Booked'
          AND check_in_date < %s
          AND check_out_date > %s
    """
    params = [room_id, check_out_date, check_in_date]

    if exclude_booking_id:
        query += " AND booking_id <> %s"
        params.append(exclude_booking_id)

    cursor.execute(query, tuple(params))
    result = cursor.fetchone()
    return result["active_count"] if result else 0


def get_room_by_id(cursor, room_id):
    cursor.execute("SELECT * FROM ROOM WHERE room_id = %s", (room_id,))
    return cursor.fetchone()


def get_rooms(filters=None):
    filters = filters or {}
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        query = "SELECT * FROM ROOM WHERE 1 = 1"
        params = []

        if filters.get("guests"):
            query += " AND capacity >= %s"
            params.append(filters["guests"])
        if filters.get("budget_max") is not None:
            query += " AND price <= %s"
            params.append(filters["budget_max"])
        if filters.get("budget_min") is not None:
            query += " AND price >= %s"
            params.append(filters["budget_min"])
        if filters.get("view_type"):
            query += " AND view_type = %s"
            params.append(filters["view_type"])

        query += " ORDER BY price ASC, room_id ASC"
        cursor.execute(query, tuple(params))
        rooms = cursor.fetchall()

        check_in_date = filters.get("check_in")
        check_out_date = filters.get("check_out")

        for room in rooms:
            if check_in_date and check_out_date:
                live_bookings = count_conflicting_bookings(
                    cursor, room["room_id"], check_in_date, check_out_date
                )
            else:
                cursor.execute(
                    """
                    SELECT COUNT(*) AS active_count
                    FROM BOOKING
                    WHERE room_id = %s
                      AND booking_status = 'Booked'
                      AND check_out_date > CURDATE()
                    """,
                    (room["room_id"],),
                )
                result = cursor.fetchone()
                live_bookings = result["active_count"] if result else 0

            room["booking_count"] = live_bookings
            room["available_slots"] = max(room["max_bookings"] - live_bookings, 0)
            room["is_available"] = room["available_slots"] > 0
            room["availability_message"] = (
                f"Only {room['available_slots']} room(s) left" if room["available_slots"] <= 2 else "Available now"
            )
            room["amenity_list"] = [item.strip() for item in (room["amenities"] or "").split(",") if item.strip()]
            room["feature_list"] = [item.strip() for item in (room["features"] or "").split(",") if item.strip()]
            room["similar_rooms"] = []

        if check_in_date and check_out_date:
            priced_rooms = list(rooms)
            for room in rooms:
                if not room["is_available"]:
                    room["similar_rooms"] = find_similar_rooms(priced_rooms, room)

        return rooms
    finally:
        cursor.close()
        connection.close()


def find_similar_rooms(rooms, target_room):
    similar = []
    target_amenities = set(target_room.get("amenity_list") or [])

    for room in rooms:
        if room["room_id"] == target_room["room_id"] or not room["is_available"]:
            continue

        price_close = abs(float(room["price"]) - float(target_room["price"])) <= 2500
        capacity_ok = room["capacity"] >= target_room["capacity"]
        overlap = len(target_amenities.intersection(set(room.get("amenity_list") or [])))

        if price_close or (capacity_ok and overlap >= 2):
            similar.append(
                {
                    "room_id": room["room_id"],
                    "room_type": room["room_type"],
                    "price": format_currency(room["price"]),
                    "capacity": room["capacity"],
                    "image_url": room["image_url"],
                    "availability_message": room["availability_message"],
                }
            )

    return similar[:3]


def get_availability_calendar(room_id, days=45):
    room = run_query("SELECT * FROM ROOM WHERE room_id = %s", (room_id,), fetchone=True)
    if not room:
        return None

    bookings = run_query(
        """
        SELECT check_in_date, check_out_date
        FROM BOOKING
        WHERE room_id = %s
          AND booking_status = 'Booked'
          AND check_out_date >= CURDATE()
        ORDER BY check_in_date ASC
        """,
        (room_id,),
    )

    blocked = set()
    for booking in bookings:
        current = booking["check_in_date"]
        while current < booking["check_out_date"]:
            blocked.add(current.isoformat())
            current += timedelta(days=1)

    today = date.today()
    calendar = []
    for offset in range(days):
        current = today + timedelta(days=offset)
        calendar.append(
            {
                "date": current.isoformat(),
                "label": current.strftime("%d %b"),
                "is_blocked": current.isoformat() in blocked,
                "weekday": current.strftime("%a"),
            }
        )

    return {"room": room, "calendar": calendar}


def create_booking_history(cursor, booking_id, user_id, action_type, previous_data=None, new_data=None, note=None):
    cursor.execute(
        """
        INSERT INTO BOOKING_HISTORY (booking_id, user_id, action_type, previous_data, new_data, note)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            booking_id,
            user_id,
            action_type,
            json.dumps(previous_data, default=str) if previous_data else None,
            json.dumps(new_data, default=str) if new_data else None,
            note,
        ),
    )


def get_upgrade_suggestions(cursor, booking):
    cursor.execute(
        """
        SELECT *
        FROM ROOM
        WHERE price > (
            SELECT price FROM ROOM WHERE room_id = %s
        )
          AND capacity >= %s
        ORDER BY price ASC
        LIMIT 2
        """,
        (booking["room_id"], booking["guest_count"]),
    )
    upgrades = cursor.fetchall()
    suggestions = []

    for room in upgrades:
        pricing = calculate_pricing(room["price"], booking["check_in_date"], booking["check_out_date"])
        price_difference = round(pricing["total"] - float(booking["total_price"]), 2)
        if price_difference <= 0:
            continue
        suggestions.append(
            {
                "room_id": room["room_id"],
                "room_type": room["room_type"],
                "price_difference": price_difference,
                "new_total": pricing["total"],
                "amenities": room["amenities"],
                "image_url": room["image_url"],
            }
        )

    return suggestions


def serialize_booking_row(booking, history_rows=None, upgrade_suggestions=None):
    booking["subtotal"] = format_currency(booking.get("subtotal"))
    booking["tax_amount"] = format_currency(booking.get("tax_amount"))
    booking["total_price"] = format_currency(booking.get("total_price"))
    booking["refund_amount"] = format_currency(booking.get("refund_amount"))
    booking["modification_history"] = history_rows or []
    booking["upgrade_suggestions"] = upgrade_suggestions or []
    booking["can_rebook"] = booking["check_out_date"] < date.today()
    booking["current_policy"] = get_cancellation_policy(booking["check_in_date"])["label"]
    return booking


def create_booking(user_id, room_id, check_in_date, check_out_date, guest_count, payment_method="Card"):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        room = get_room_by_id(cursor, room_id)
        if not room:
            raise ValueError("Room not found.")
        if guest_count > room["capacity"]:
            raise ValueError("Selected room cannot accommodate that many guests.")
        if check_in_date < date.today():
            raise ValueError("Check-in date cannot be in the past.")
        if count_conflicting_bookings(cursor, room_id, check_in_date, check_out_date) >= room["max_bookings"]:
            raise ValueError("This room is unavailable for the selected dates.")

        pricing = calculate_pricing(room["price"], check_in_date, check_out_date)
        policy = get_cancellation_policy(check_in_date)

        cursor.execute(
            "SELECT full_name, phone, email FROM USERS WHERE user_id = %s",
            (user_id,),
        )
        user = cursor.fetchone()
        ensure_customer_profile(cursor, user_id, user["full_name"], user["phone"], user["email"])

        invoice_number = f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}-{user_id}"
        payment_reference = f"PAY-{datetime.now().strftime('%Y%m%d%H%M%S')}-{room_id}"

        cursor.execute(
            """
            INSERT INTO BOOKING(
                user_id, room_id, check_in_date, check_out_date, booking_date,
                status, booking_status, guest_count, subtotal, tax_amount, total_price,
                payment_status, payment_method, payment_reference, cancellation_policy,
                refund_amount, invoice_number
            )
            VALUES (%s, %s, %s, %s, NOW(), 'Confirmed', 'Booked', %s, %s, %s, %s, 'Completed', %s, %s, %s, 0, %s)
            """,
            (
                user_id,
                room_id,
                check_in_date,
                check_out_date,
                guest_count,
                pricing["subtotal"],
                pricing["tax_amount"],
                pricing["total"],
                payment_method,
                payment_reference,
                policy["label"],
                invoice_number,
            ),
        )
        booking_id = cursor.lastrowid
        create_booking_history(
            cursor,
            booking_id,
            user_id,
            "created",
            note="Booking created successfully.",
            new_data={
                "room_id": room_id,
                "check_in_date": check_in_date,
                "check_out_date": check_out_date,
                "guest_count": guest_count,
                "pricing": pricing,
            },
        )
        connection.commit()
        return get_booking_details(booking_id, user_id=user_id, cursor=cursor)
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def get_booking_details(booking_id, user_id=None, cursor=None):
    own_connection = cursor is None
    if own_connection:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

    try:
        query = """
            SELECT
                B.*,
                R.room_type,
                R.capacity,
                R.amenities,
                R.floor_level,
                R.view_type,
                R.image_url,
                R.description,
                R.features,
                U.full_name,
                U.email,
                U.phone
            FROM BOOKING B
            JOIN ROOM R ON R.room_id = B.room_id
            JOIN USERS U ON U.user_id = B.user_id
            WHERE B.booking_id = %s
        """
        params = [booking_id]
        if user_id:
            query += " AND B.user_id = %s"
            params.append(user_id)

        cursor.execute(query, tuple(params))
        booking = cursor.fetchone()
        if not booking:
            return None

        cursor.execute(
            "SELECT * FROM BOOKING_HISTORY WHERE booking_id = %s ORDER BY created_at DESC",
            (booking_id,),
        )
        history_rows = cursor.fetchall()
        for row in history_rows:
            row["previous_data"] = json.loads(row["previous_data"]) if row["previous_data"] else None
            row["new_data"] = json.loads(row["new_data"]) if row["new_data"] else None

        upgrades = []
        if booking["booking_status"] == "Booked":
            upgrades = get_upgrade_suggestions(cursor, booking)

        return serialize_booking_row(booking, history_rows, upgrades)
    finally:
        if own_connection:
            cursor.close()
            connection.close()


def list_user_bookings(user_id):
    bookings = run_query(
        """
        SELECT
            B.booking_id
        FROM BOOKING B
        WHERE B.user_id = %s
        ORDER BY B.booking_date DESC
        """,
        (user_id,),
    )
    return [get_booking_details(row["booking_id"], user_id=user_id) for row in bookings]


def update_booking(booking_id, user_id, room_id, check_in_date, check_out_date, guest_count):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        booking = get_booking_details(booking_id, user_id=user_id, cursor=cursor)
        if not booking:
            raise ValueError("Booking not found.")
        if booking["booking_status"] != "Booked":
            raise ValueError("Only active bookings can be modified.")

        room = get_room_by_id(cursor, room_id)
        if not room:
            raise ValueError("Selected room not found.")
        if guest_count > room["capacity"]:
            raise ValueError("Selected room cannot accommodate that many guests.")
        if check_in_date < date.today():
            raise ValueError("Check-in date cannot be in the past.")

        conflicts = count_conflicting_bookings(
            cursor, room_id, check_in_date, check_out_date, exclude_booking_id=booking_id
        )
        if conflicts >= room["max_bookings"]:
            raise ValueError("Selected room is not available for the updated dates.")

        pricing = calculate_pricing(room["price"], check_in_date, check_out_date)
        policy = get_cancellation_policy(check_in_date)

        previous_data = {
            "room_id": booking["room_id"],
            "room_type": booking["room_type"],
            "check_in_date": booking["check_in_date"],
            "check_out_date": booking["check_out_date"],
            "guest_count": booking["guest_count"],
            "total_price": booking["total_price"],
        }
        new_data = {
            "room_id": room_id,
            "room_type": room["room_type"],
            "check_in_date": check_in_date,
            "check_out_date": check_out_date,
            "guest_count": guest_count,
            "total_price": pricing["total"],
        }

        cursor.execute(
            """
            UPDATE BOOKING
            SET room_id = %s,
                check_in_date = %s,
                check_out_date = %s,
                guest_count = %s,
                subtotal = %s,
                tax_amount = %s,
                total_price = %s,
                cancellation_policy = %s,
                modified_at = NOW(),
                modification_count = modification_count + 1
            WHERE booking_id = %s
            """,
            (
                room_id,
                check_in_date,
                check_out_date,
                guest_count,
                pricing["subtotal"],
                pricing["tax_amount"],
                pricing["total"],
                policy["label"],
                booking_id,
            ),
        )
        create_booking_history(
            cursor,
            booking_id,
            user_id,
            "modified",
            previous_data=previous_data,
            new_data=new_data,
            note="Booking updated by customer.",
        )
        connection.commit()
        return get_booking_details(booking_id, user_id=user_id, cursor=cursor)
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def cancel_booking(booking_id, user_id, reason=None):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        booking = get_booking_details(booking_id, user_id=user_id, cursor=cursor)
        if not booking:
            raise ValueError("Booking not found.")
        if booking["booking_status"] == "Cancelled":
            raise ValueError("Booking is already cancelled.")

        refund = calculate_refund(booking["total_price"], booking["check_in_date"])
        cursor.execute(
            """
            UPDATE BOOKING
            SET status = 'Cancelled',
                booking_status = 'Cancelled',
                payment_status = %s,
                refund_amount = %s,
                cancellation_policy = %s,
                cancellation_reason = %s,
                cancelled_at = NOW()
            WHERE booking_id = %s
            """,
            (
                "Refunded" if refund["refund_amount"] > 0 else "No Refund",
                refund["refund_amount"],
                refund["policy"],
                reason,
                booking_id,
            ),
        )
        create_booking_history(
            cursor,
            booking_id,
            user_id,
            "cancelled",
            previous_data={"booking_status": "Booked"},
            new_data={"booking_status": "Cancelled", "refund_amount": refund["refund_amount"]},
            note=reason or "Booking cancelled.",
        )
        connection.commit()
        return get_booking_details(booking_id, user_id=user_id, cursor=cursor)
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def upgrade_booking(booking_id, user_id, new_room_id):
    booking = get_booking_details(booking_id, user_id=user_id)
    if not booking:
        raise ValueError("Booking not found.")
    return update_booking(
        booking_id,
        user_id,
        new_room_id,
        booking["check_in_date"],
        booking["check_out_date"],
        booking["guest_count"],
    )


def get_admin_metrics():
    metrics = run_query(
        """
        SELECT
            COUNT(*) AS total_bookings,
            SUM(CASE WHEN booking_status = 'Booked' THEN 1 ELSE 0 END) AS confirmed_bookings,
            SUM(CASE WHEN booking_status = 'Cancelled' THEN 1 ELSE 0 END) AS cancelled_bookings,
            COALESCE(SUM(total_price), 0) AS gross_revenue,
            COALESCE(SUM(refund_amount), 0) AS refunds_paid
        FROM BOOKING
        """,
        fetchone=True,
    )
    customers = run_query(
        "SELECT COUNT(*) AS total_customers FROM USERS WHERE role = 'customer'",
        fetchone=True,
    )
    rooms = run_query(
        "SELECT COUNT(*) AS total_rooms, COALESCE(SUM(max_bookings), 0) AS room_inventory FROM ROOM",
        fetchone=True,
    )
    payments = run_query(
        """
        SELECT
            booking_id,
            booking_date,
            total_price,
            payment_status,
            payment_method,
            payment_reference,
            invoice_number
        FROM BOOKING
        ORDER BY booking_date DESC
        LIMIT 6
        """
    )
    return {
        "total_bookings": int(metrics["total_bookings"] or 0),
        "confirmed_bookings": int(metrics["confirmed_bookings"] or 0),
        "cancelled_bookings": int(metrics["cancelled_bookings"] or 0),
        "gross_revenue": format_currency(metrics["gross_revenue"]),
        "refunds_paid": format_currency(metrics["refunds_paid"]),
        "net_revenue": format_currency(float(metrics["gross_revenue"] or 0) - float(metrics["refunds_paid"] or 0)),
        "total_customers": int(customers["total_customers"] or 0),
        "total_rooms": int(rooms["total_rooms"] or 0),
        "room_inventory": int(rooms["room_inventory"] or 0),
        "recent_payments": payments,
    }


def get_admin_bookings(search=None, status=None):
    query = """
        SELECT
            B.booking_id,
            B.booking_date,
            B.check_in_date,
            B.check_out_date,
            B.booking_status,
            B.payment_status,
            B.payment_method,
            B.payment_reference,
            B.invoice_number,
            B.guest_count,
            B.total_price,
            B.refund_amount,
            B.cancellation_policy,
            R.room_type,
            U.full_name AS customer_name,
            U.email AS customer_email,
            U.phone AS customer_phone
        FROM BOOKING B
        JOIN ROOM R ON R.room_id = B.room_id
        JOIN USERS U ON U.user_id = B.user_id
        WHERE 1 = 1
    """
    params = []
    if search:
        query += " AND (U.full_name LIKE %s OR U.email LIKE %s OR U.phone LIKE %s)"
        token = f"%{search}%"
        params.extend([token, token, token])
    if status:
        query += " AND B.booking_status = %s"
        params.append(status)
    query += " ORDER BY B.booking_date DESC"
    return run_query(query, tuple(params))


def get_admin_customers(search=None):
    query = """
        SELECT
            U.user_id,
            U.full_name,
            U.email,
            U.phone,
            U.created_at,
            COUNT(B.booking_id) AS booking_count,
            COALESCE(SUM(B.total_price), 0) AS total_spent,
            COALESCE(SUM(B.refund_amount), 0) AS refunds_received,
            MAX(B.booking_date) AS last_booking_date
        FROM USERS U
        LEFT JOIN BOOKING B ON B.user_id = U.user_id
        WHERE U.role = 'customer'
    """
    params = []
    if search:
        query += " AND (U.full_name LIKE %s OR U.email LIKE %s OR U.phone LIKE %s)"
        token = f"%{search}%"
        params.extend([token, token, token])
    query += " GROUP BY U.user_id ORDER BY U.created_at DESC"
    return run_query(query, tuple(params))


def get_admin_rooms():
    return get_rooms()


def get_admin_payments(search=None, payment_status=None):
    query = """
        SELECT
            B.booking_id,
            B.booking_date,
            B.invoice_number,
            B.payment_reference,
            B.payment_method,
            B.payment_status,
            B.total_price,
            B.refund_amount,
            U.full_name AS customer_name,
            U.email AS customer_email,
            R.room_type
        FROM BOOKING B
        JOIN USERS U ON U.user_id = B.user_id
        JOIN ROOM R ON R.room_id = B.room_id
        WHERE 1 = 1
    """
    params = []
    if search:
        query += " AND (U.full_name LIKE %s OR U.email LIKE %s OR B.invoice_number LIKE %s)"
        token = f"%{search}%"
        params.extend([token, token, token])
    if payment_status:
        query += " AND B.payment_status = %s"
        params.append(payment_status)
    query += " ORDER BY B.booking_date DESC"
    return run_query(query, tuple(params))
