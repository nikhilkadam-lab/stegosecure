import hashlib
from db import get_db_connection

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username, email, password):
    conn = get_db_connection()
    cursor = conn.cursor()

    password_hash = hash_password(password)

    try:
        cursor.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
            (username, email, password_hash)
        )
        user_id = cursor.lastrowid

        # Fetch current default limit
        cursor.execute(
        "SELECT setting_value FROM system_settings WHERE setting_key = 'default_encryption_limit'"
        ) 
        row = cursor.fetchone()
        default_limit = int(row[0]) if row else 5

# Apply default limit ONLY ON REGISTRATION
        cursor.execute(
        "INSERT INTO encryption_limits (user_id, remaining_attempts) VALUES (%s, %s)",
        (user_id, default_limit)
        )

        conn.commit()
        return True
    except Exception as e:
        print(e)
        return False
    finally:
        conn.close()

def login_user(email, password):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    password_hash = hash_password(password)

    cursor.execute(
        "SELECT * FROM users WHERE email=%s AND password_hash=%s",
        (email, password_hash)
    )

    user = cursor.fetchone()
    conn.close()
    return user

def get_remaining_attempts(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT remaining_attempts FROM encryption_limits WHERE user_id = %s",
        (user_id,)
    )
    row = cursor.fetchone()
    conn.close()

    # If user has a row, return remaining attempts
    if row:
        return row[0]

    # If no row exists, return 0 (do NOT insert here)
    return 0


def decrement_attempt(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE encryption_limits SET remaining_attempts = remaining_attempts - 1 WHERE user_id=%s AND remaining_attempts > 0",
        (user_id,)
    )
    conn.commit()
    conn.close()

# ================================
# GALLERY HELPERS
# ================================

def save_encrypted_image(user_id, image_path):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO gallery (user_id, image_path) VALUES (%s, %s)",
        (user_id, image_path)
    )
    conn.commit()
    conn.close()


def get_user_uploads(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT id, image_path, uploaded_at FROM gallery WHERE user_id=%s ORDER BY uploaded_at DESC",
        (user_id,)
    )
    results = cursor.fetchall()
    conn.close()
    return results

# ================================
# DELETE USER UPLOAD
# ================================

def delete_user_upload(user_id, upload_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check ownership and get file path
    cursor.execute(
        "SELECT image_path FROM gallery WHERE id=%s AND user_id=%s",
        (upload_id, user_id)
    )
    result = cursor.fetchone()

    if not result:
        conn.close()
        return None

    image_path = result[0]

    # Delete DB record
    cursor.execute(
        "DELETE FROM gallery WHERE id=%s AND user_id=%s",
        (upload_id, user_id)
    )
    conn.commit()
    conn.close()

    return image_path
