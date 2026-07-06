import hashlib
from db import get_db_connection

def admin_login(username, password):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    password_hash = hashlib.sha256(password.encode()).hexdigest()

    cursor.execute(
        "SELECT id FROM admins WHERE username=%s AND password_hash=%s",
        (username, password_hash)
    )

    admin = cursor.fetchone()
    conn.close()

    return admin
