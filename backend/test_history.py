from db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("INSERT INTO BOOKING_HISTORY (booking_id, user_id, action_type, note) VALUES (10, 2, 'created', 'Test history entry')")
conn.commit()
conn.close()
print('Test history record inserted')