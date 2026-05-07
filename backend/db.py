import hashlib
import os

import mysql.connector


ROOM_SEEDS = [
    {
        "room_type": "Single Room",
        "price": 2500.00,
        "location": "City Wing",
        "rating": 4.2,
        "capacity": 1,
        "amenities": "WiFi, AC, TV, Bathroom, Workspace",
        "max_bookings": 6,
        "floor_level": 2,
        "view_type": "City",
        "image_url": "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=1200&q=80",
        "description": "A compact premium room for solo travelers with fast WiFi and a quiet work corner.",
        "features": "Smart TV, Tea Station, Work Desk",
    },
    {
        "room_type": "Double Room",
        "price": 4000.00,
        "location": "Garden Wing",
        "rating": 4.5,
        "capacity": 2,
        "amenities": "WiFi, AC, TV, Bathroom, Balcony, Mini Bar",
        "max_bookings": 8,
        "floor_level": 4,
        "view_type": "Garden",
        "image_url": "https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?auto=format&fit=crop&w=1200&q=80",
        "description": "A warm room for couples or friends with a balcony overlooking the hotel gardens.",
        "features": "Balcony, Rain Shower, Mini Bar",
    },
    {
        "room_type": "Deluxe Suite",
        "price": 6500.00,
        "location": "Ocean Wing",
        "rating": 4.8,
        "capacity": 4,
        "amenities": "WiFi, AC, TV, Bathroom, Balcony, Mini Bar, Jacuzzi, Lounge",
        "max_bookings": 5,
        "floor_level": 6,
        "view_type": "Sea",
        "image_url": "https://images.unsplash.com/photo-1566665797739-1674de7a421a?auto=format&fit=crop&w=1200&q=80",
        "description": "A spacious suite with a lounge area, jacuzzi, and premium sea-facing experience.",
        "features": "Sea View, Jacuzzi, Lounge Area",
    },
    {
        "room_type": "Executive Panorama Suite",
        "price": 8200.00,
        "location": "Skyline Tower",
        "rating": 4.9,
        "capacity": 4,
        "amenities": "WiFi, AC, TV, Bathroom, Balcony, Mini Bar, Lounge, Butler Service, Breakfast",
        "max_bookings": 3,
        "floor_level": 8,
        "view_type": "Sea",
        "image_url": "https://images.unsplash.com/photo-1551882547-ff40c63fe5fa?auto=format&fit=crop&w=1200&q=80",
        "description": "A signature suite with panoramic windows, elevated amenities, and complimentary breakfast.",
        "features": "Panorama Windows, Butler Service, Breakfast Included",
    },
    {
        "room_type": "Garden Twin Retreat",
        "price": 4600.00,
        "location": "Garden Wing",
        "rating": 4.4,
        "capacity": 2,
        "amenities": "WiFi, AC, Smart TV, Bathroom, Garden Balcony, Coffee Station",
        "max_bookings": 6,
        "floor_level": 3,
        "view_type": "Garden",
        "image_url": "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=1200&q=80",
        "description": "A calm twin room with leafy balcony views and warm wood finishes for slow mornings.",
        "features": "Twin Beds, Garden Balcony, Coffee Station",
    },
    {
        "room_type": "Premier City King",
        "price": 5400.00,
        "location": "City Wing",
        "rating": 4.6,
        "capacity": 3,
        "amenities": "WiFi, AC, Smart TV, Bathroom, Lounge Chair, Mini Bar, Espresso Machine",
        "max_bookings": 7,
        "floor_level": 5,
        "view_type": "City",
        "image_url": "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=1200&q=80",
        "description": "A polished king room with skyline views, rich textures, and space to unwind after a long day.",
        "features": "King Bed, Skyline View, Espresso Machine",
    },
    {
        "room_type": "Family Garden Suite",
        "price": 7200.00,
        "location": "Garden Wing",
        "rating": 4.7,
        "capacity": 5,
        "amenities": "WiFi, AC, Smart TV, Bathroom, Kids Nook, Lounge, Mini Bar, Breakfast",
        "max_bookings": 4,
        "floor_level": 4,
        "view_type": "Garden",
        "image_url": "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=1200&q=80",
        "description": "A roomy family suite with flexible sleeping arrangements and a bright garden outlook.",
        "features": "Family Lounge, Kids Nook, Breakfast Included",
    },
    {
        "room_type": "Sunset Terrace Suite",
        "price": 9100.00,
        "location": "Ocean Wing",
        "rating": 4.9,
        "capacity": 4,
        "amenities": "WiFi, AC, Smart TV, Bathroom, Private Terrace, Mini Bar, Lounge, Bathtub",
        "max_bookings": 3,
        "floor_level": 7,
        "view_type": "Sea",
        "image_url": "https://images.unsplash.com/photo-1551882547-ff40c63fe5fa?auto=format&fit=crop&w=1200&q=80",
        "description": "A high-floor suite with a private terrace and golden-hour views designed for special stays.",
        "features": "Private Terrace, Sunset View, Soaking Tub",
    },
    {
        "room_type": "Royal Presidential Loft",
        "price": 12500.00,
        "location": "Skyline Tower",
        "rating": 5.0,
        "capacity": 6,
        "amenities": "WiFi, AC, Smart TV, Bathroom, Dining Area, Butler Service, Jacuzzi, Private Bar, Breakfast",
        "max_bookings": 2,
        "floor_level": 9,
        "view_type": "Sea",
        "image_url": "https://images.unsplash.com/photo-1566665797739-1674de7a421a?auto=format&fit=crop&w=1200&q=80",
        "description": "A statement-making loft with expansive entertaining space, private service, and signature coastal views.",
        "features": "Private Bar, Butler Service, Dining Loft",
    },
]


def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", "nidhica"),
        database=os.getenv("DB_NAME", "hotel_db"),
    )


def run_query(query, params=None, fetchone=False):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(query, params or ())
        result = cursor.fetchone() if fetchone else cursor.fetchall()
        return result
    finally:
        cursor.close()
        connection.close()


def bootstrap_database():
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS USERS (
              user_id INT AUTO_INCREMENT PRIMARY KEY,
              email VARCHAR(100) UNIQUE NOT NULL,
              password VARCHAR(255) NOT NULL,
              full_name VARCHAR(100) NOT NULL,
              phone VARCHAR(20) NOT NULL,
              role ENUM('customer', 'admin') NOT NULL DEFAULT 'customer',
              created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ROOM (
              room_id INT AUTO_INCREMENT PRIMARY KEY,
              room_type VARCHAR(100) NOT NULL,
              price DECIMAL(10, 2) NOT NULL,
              location VARCHAR(100) DEFAULT 'Main Wing',
              rating DECIMAL(3, 2) DEFAULT 4.00,
              total_reviews INT NOT NULL DEFAULT 0,
              capacity INT NOT NULL DEFAULT 2,
              amenities VARCHAR(500),
              max_bookings INT NOT NULL DEFAULT 10,
              floor_level INT DEFAULT 1,
              view_type VARCHAR(50) DEFAULT 'City',
              image_url VARCHAR(500),
              description TEXT,
              features VARCHAR(500)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS CUSTOMER (
              cust_id INT AUTO_INCREMENT PRIMARY KEY,
              user_id INT NOT NULL UNIQUE,
              name VARCHAR(100) NOT NULL,
              phone VARCHAR(20) NOT NULL,
              email VARCHAR(100),
              created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
              CONSTRAINT fk_customer_user FOREIGN KEY (user_id) REFERENCES USERS(user_id) ON DELETE CASCADE
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS BOOKING (
              booking_id INT AUTO_INCREMENT PRIMARY KEY,
              user_id INT NOT NULL,
              room_id INT NOT NULL,
              check_in_date DATE NOT NULL,
              check_out_date DATE NOT NULL,
              booking_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              status VARCHAR(20) NOT NULL DEFAULT 'Confirmed',
              booking_status VARCHAR(30) NOT NULL DEFAULT 'Booked',
              guest_count INT NOT NULL DEFAULT 1,
              subtotal DECIMAL(10, 2) NOT NULL DEFAULT 0,
              tax_amount DECIMAL(10, 2) NOT NULL DEFAULT 0,
              total_price DECIMAL(10, 2) NOT NULL DEFAULT 0,
              payment_status VARCHAR(30) NOT NULL DEFAULT 'Pending',
              payment_method VARCHAR(30) NOT NULL DEFAULT 'Card',
              payment_reference VARCHAR(100),
              cancellation_policy VARCHAR(40) NOT NULL DEFAULT 'Free',
              refund_amount DECIMAL(10, 2) NOT NULL DEFAULT 0,
              cancellation_reason VARCHAR(255),
              cancelled_at DATETIME NULL,
              modified_at DATETIME NULL,
              modification_count INT NOT NULL DEFAULT 0,
              invoice_number VARCHAR(50),
              CONSTRAINT fk_booking_user FOREIGN KEY (user_id) REFERENCES USERS(user_id) ON DELETE CASCADE,
              CONSTRAINT fk_booking_room FOREIGN KEY (room_id) REFERENCES ROOM(room_id),
              INDEX idx_room_dates (room_id, check_in_date, check_out_date),
              INDEX idx_user_dates (user_id, check_in_date, check_out_date)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS BOOKING_HISTORY (
              history_id INT AUTO_INCREMENT PRIMARY KEY,
              booking_id INT NOT NULL,
              user_id INT NOT NULL,
              action_type VARCHAR(30) NOT NULL,
              previous_data TEXT,
              new_data TEXT,
              note VARCHAR(255),
              created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              CONSTRAINT fk_history_booking FOREIGN KEY (booking_id) REFERENCES BOOKING(booking_id) ON DELETE CASCADE,
              CONSTRAINT fk_history_user FOREIGN KEY (user_id) REFERENCES USERS(user_id) ON DELETE CASCADE
            )
            """
        )

        # Add user_id column if it doesn't exist (for backward compatibility)
        try:
            cursor.execute("ALTER TABLE BOOKING_HISTORY ADD COLUMN user_id INT NOT NULL DEFAULT 1")
            cursor.execute("ALTER TABLE BOOKING_HISTORY ADD CONSTRAINT fk_history_user FOREIGN KEY (user_id) REFERENCES USERS(user_id) ON DELETE CASCADE")
        except:
            pass  # Column might already exist

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS WISHLIST (
              wishlist_id INT AUTO_INCREMENT PRIMARY KEY,
              user_id INT NOT NULL,
              room_id INT NOT NULL,
              added_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              CONSTRAINT fk_wishlist_user FOREIGN KEY (user_id) REFERENCES USERS(user_id) ON DELETE CASCADE,
              CONSTRAINT fk_wishlist_room FOREIGN KEY (room_id) REFERENCES ROOM(room_id) ON DELETE CASCADE,
              UNIQUE KEY uq_user_room (user_id, room_id),
              INDEX idx_user_wishlist (user_id, added_at),
              INDEX idx_room_wishlist (room_id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS REVIEW (
              review_id INT AUTO_INCREMENT PRIMARY KEY,
              booking_id INT NOT NULL,
              user_id INT NOT NULL,
              room_id INT NOT NULL,
              rating INT NOT NULL,
              review_text TEXT,
              created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
              CONSTRAINT chk_review_rating CHECK (rating BETWEEN 1 AND 5),
              CONSTRAINT fk_review_booking FOREIGN KEY (booking_id) REFERENCES BOOKING(booking_id) ON DELETE CASCADE,
              CONSTRAINT fk_review_user FOREIGN KEY (user_id) REFERENCES USERS(user_id) ON DELETE CASCADE,
              CONSTRAINT fk_review_room FOREIGN KEY (room_id) REFERENCES ROOM(room_id) ON DELETE CASCADE,
              UNIQUE KEY uq_review_booking (booking_id),
              INDEX idx_review_room (room_id),
              INDEX idx_review_user (user_id)
            )
            """
        )

        _ensure_room_extensions(cursor)
        _ensure_booking_extensions(cursor)
        _seed_rooms(cursor)
        _sync_room_review_metrics(cursor)

        admin_password = hash_password("admin123")
        customer_password = hash_password("customer123")

        cursor.execute(
            """
            INSERT INTO USERS (email, password, full_name, phone, role)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE password = VALUES(password), full_name = VALUES(full_name), phone = VALUES(phone), role = VALUES(role)
            """,
            ("admin@hotel.com", admin_password, "Admin User", "9999999999", "admin"),
        )
        cursor.execute(
            """
            INSERT INTO USERS (email, password, full_name, phone, role)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE password = VALUES(password), full_name = VALUES(full_name), phone = VALUES(phone), role = VALUES(role)
            """,
            ("customer@hotel.com", customer_password, "Demo Customer", "8888888888", "customer"),
        )

        cursor.execute(
            """
            INSERT INTO CUSTOMER (user_id, name, phone, email)
            SELECT user_id, full_name, phone, email
            FROM USERS
            WHERE role = 'customer'
            ON DUPLICATE KEY UPDATE name = VALUES(name), phone = VALUES(phone), email = VALUES(email)
            """
        )

        connection.commit()
    finally:
        cursor.close()
        connection.close()


def _column_exists(cursor, table_name, column_name):
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        """,
        (table_name, column_name),
    )
    return cursor.fetchone()[0] > 0


def _ensure_booking_extensions(cursor):
    booking_columns = {
        "booking_status": "ALTER TABLE BOOKING ADD COLUMN booking_status VARCHAR(30) NOT NULL DEFAULT 'Booked' AFTER status",
        "guest_count": "ALTER TABLE BOOKING ADD COLUMN guest_count INT NOT NULL DEFAULT 1 AFTER booking_status",
        "cancellation_policy": "ALTER TABLE BOOKING ADD COLUMN cancellation_policy VARCHAR(40) NOT NULL DEFAULT 'Free' AFTER guest_count",
        "refund_amount": "ALTER TABLE BOOKING ADD COLUMN refund_amount DECIMAL(10, 2) NOT NULL DEFAULT 0 AFTER cancellation_policy",
        "modification_history": "ALTER TABLE BOOKING ADD COLUMN modification_history JSON NULL AFTER refund_amount",
    }

    for column_name, statement in booking_columns.items():
        if not _column_exists(cursor, "BOOKING", column_name):
            cursor.execute(statement)

    if _column_exists(cursor, "BOOKING", "status"):
        cursor.execute(
            """
            UPDATE BOOKING
            SET booking_status = CASE
                WHEN status = 'Cancelled' THEN 'Cancelled'
                WHEN check_out_date < CURDATE() THEN 'Completed'
                ELSE 'Booked'
            END
            WHERE booking_status IS NULL OR booking_status = '' OR booking_status = 'Confirmed'
            """
        )


def _ensure_room_extensions(cursor):
    room_columns = {
        "location": "ALTER TABLE ROOM ADD COLUMN location VARCHAR(100) DEFAULT 'Main Wing' AFTER price",
        "rating": "ALTER TABLE ROOM ADD COLUMN rating DECIMAL(3, 2) DEFAULT 4.00 AFTER location",
        "total_reviews": "ALTER TABLE ROOM ADD COLUMN total_reviews INT NOT NULL DEFAULT 0 AFTER rating",
        "floor_level": "ALTER TABLE ROOM ADD COLUMN floor_level INT DEFAULT 1 AFTER max_bookings",
        "view_type": "ALTER TABLE ROOM ADD COLUMN view_type VARCHAR(50) DEFAULT 'City' AFTER floor_level",
        "image_url": "ALTER TABLE ROOM ADD COLUMN image_url VARCHAR(500) NULL AFTER view_type",
        "description": "ALTER TABLE ROOM ADD COLUMN description TEXT NULL AFTER image_url",
        "features": "ALTER TABLE ROOM ADD COLUMN features VARCHAR(500) NULL AFTER description",
    }

    for column_name, statement in room_columns.items():
        if not _column_exists(cursor, "ROOM", column_name):
            cursor.execute(statement)

    room_indexes = {
        "idx_room_price": "CREATE INDEX idx_room_price ON ROOM(price)",
        "idx_room_location": "CREATE INDEX idx_room_location ON ROOM(location)",
        "idx_room_rating": "CREATE INDEX idx_room_rating ON ROOM(rating)",
    }

    for index_name, statement in room_indexes.items():
        if not _index_exists(cursor, "ROOM", index_name):
            cursor.execute(statement)


def _seed_rooms(cursor):
    for room in ROOM_SEEDS:
        cursor.execute("SELECT room_id FROM ROOM WHERE room_type = %s", (room["room_type"],))
        existing = cursor.fetchone()
        values = (
            room["price"],
            room["location"],
            room["rating"],
            0,
            room["capacity"],
            room["amenities"],
            room["max_bookings"],
            room["floor_level"],
            room["view_type"],
            room["image_url"],
            room["description"],
            room["features"],
        )
        if existing:
            cursor.execute(
                """
                UPDATE ROOM
                SET price = %s,
                    location = %s,
                    rating = %s,
                    total_reviews = %s,
                    capacity = %s,
                    amenities = %s,
                    max_bookings = %s,
                    floor_level = %s,
                    view_type = %s,
                    image_url = %s,
                    description = %s,
                    features = %s
                WHERE room_id = %s
                """,
                values + (existing[0],),
            )
        else:
            cursor.execute(
                """
                INSERT INTO ROOM(
                    room_type, price, location, rating, total_reviews, capacity, amenities, max_bookings,
                    floor_level, view_type, image_url, description, features
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (room["room_type"],) + values,
            )


def _index_exists(cursor, table_name, index_name):
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND INDEX_NAME = %s
        """,
        (table_name, index_name),
    )
    return cursor.fetchone()[0] > 0


def _sync_room_review_metrics(cursor):
    cursor.execute(
        """
        UPDATE ROOM R
        LEFT JOIN (
            SELECT room_id, ROUND(AVG(rating), 2) AS average_rating, COUNT(*) AS review_count
            FROM REVIEW
            GROUP BY room_id
        ) RV ON R.room_id = RV.room_id
        SET R.rating = COALESCE(RV.average_rating, R.rating),
            R.total_reviews = COALESCE(RV.review_count, 0)
        """
    )
