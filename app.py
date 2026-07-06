from flask import Flask, request, send_file, jsonify
import os, json, io
import razorpay
from filename_utils import normalize_output_filename
from flask_cors import CORS

# ===== IMPORT HELPERS =====
from auth import (
    register_user,
    login_user,
    get_remaining_attempts,
    decrement_attempt,
    save_encrypted_image,
    get_user_uploads,
    delete_user_upload,
    get_db_connection
)


RAZORPAY_KEY_ID = "rzp_test_S6WscdakdcZUgs"
RAZORPAY_KEY_SECRET = "vdFogrArqs8Jm8s9Ooyu6DzN"

razorpay_client = razorpay.Client(
    auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)
)

from stego_lsb import embed_text, extract_text
from crypto_utils import aes_encrypt, aes_decrypt
from auth_utils import sha256_hash
from file_utils import file_to_base64, base64_to_file

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = "Uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# =================================================
# BASIC CHECK
# =================================================
@app.route("/")
def home():
    return "Merged backend running"


# =================================================
# ADMIN AUTH
# =================================================
@app.route("/admin/login", methods=["POST"])
def admin_login():
    data = request.json or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return {"error": "Missing credentials"}, 400

    password_hash = sha256_hash(password)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT id FROM admins WHERE username=%s AND password_hash=%s",
        (username, password_hash)
    )
    admin = cursor.fetchone()
    conn.close()

    if not admin:
        return {"error": "Invalid admin credentials"}, 401

    return {"message": "Admin login successful", "admin_id": admin["id"]}

# =================================================
# ADMIN VIEW USERS
# =================================================

@app.route("/admin/users", methods=["GET"])
def admin_view_users():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT u.id, u.username, u.email,u.created_at,
               IFNULL(e.remaining_attempts, 0) AS remaining_attempts
        FROM users u
        LEFT JOIN encryption_limits e ON u.id = e.user_id
    """)
    users = cursor.fetchall()
    conn.close()

    return {"users": users}



# =================================================
# ADMIN VIEW PATMENT
# =================================================

@app.route("/admin/payments", methods=["GET"])
def admin_view_payments():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT p.id, p.user_id, u.username,
               p.amount, p.status, p.created_at,p.payment_id,
               pl.name AS plan_name, pl.encryptions
        FROM payments p
        JOIN users u ON p.user_id = u.id
        JOIN plans pl ON p.plan_id = pl.id
        ORDER BY p.created_at DESC
    """)
    payments = cursor.fetchall()
    conn.close()

    return {"payments": payments}

# =================================================
# ADMIN GET LIMIT & UPDATE LIMIT
# =================================================
@app.route("/admin/get-default-limit", methods=["GET"])
def get_default_limit():
    """Get current default encryption limit"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute(
        "SELECT setting_value FROM system_settings WHERE setting_key = 'default_encryption_limit'"
    )
    
    result = cursor.fetchone()
    conn.close()
    
    default_limit = 0
    if result and result['setting_value']:
        default_limit = int(result['setting_value'])
    
    return {"default_limit": default_limit}

@app.route("/admin/update-limit", methods=["POST"])
def admin_update_limit():
    data = request.json or {}
    user_id = data.get("user_id")
    new_limit = data.get("new_limit")

    if user_id is None or new_limit is None:
        return {"error": "Missing data"}, 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE encryption_limits SET remaining_attempts=%s WHERE user_id=%s",
        (int(new_limit), int(user_id))
    )

    conn.commit()
    conn.close()

    return {"message": "Encryption limit updated"}

# =================================================
# TO SET DEFAULT LIMIT
# =================================================
@app.route("/admin/update-default-limit", methods=["POST"])
def admin_update_default_limit():
    data = request.json or {}
    new_limit = data.get("new_limit")

    if new_limit is None:
        return {"error": "Missing new_limit"}, 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO system_settings (setting_key, setting_value)
        VALUES ('default_encryption_limit', %s)
        ON DUPLICATE KEY UPDATE setting_value = %s
        """,
        (int(new_limit), int(new_limit))
    )

    conn.commit()
    conn.close()

    return {
        "message": "Default encryption limit updated (applies to new users only)",
        "new_default_limit": int(new_limit)
    }

# =================================================
# TO UPDATE PLAN
# =================================================
@app.route("/admin/update-plan", methods=["POST"])
def admin_update_plan():
    data = request.json or {}

    plan_id = data.get("plan_id")
    price = data.get("price")
    encryptions = data.get("encryptions")

    if not plan_id or price is None or encryptions is None:
        return {"error": "Missing plan data"}, 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE plans
        SET price = %s, encryptions = %s
        WHERE id = %s
        """,
        (int(price), int(encryptions), int(plan_id))
    )

    conn.commit()
    conn.close()

    return {
        "message": "Plan updated successfully",
        "plan_id": plan_id,
        "price": price,
        "encryptions": encryptions
    }


# =================================================
# USER AUTH
# =================================================
@app.route("/register", methods=["POST"])
def register():
    data = request.json
    success = register_user(
        data["username"],
        data["email"],
        data["password"]
    )
    return {"success": success}


@app.route("/login", methods=["POST"])
def login():
    data = request.json or {}

    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return {"error": "Email and password required"}, 400

    user = login_user(email, password)

    if user:
        return {
            "success": True,
            "user_id": user["id"],
            "username": user["username"]
        }

    return {"success": False}, 401



# =================================================
# BASIC LSB TEXT (NO AES)
# =================================================
@app.route("/embed-text", methods=["POST"])
def embed_plain_text():
    image = request.files["image"]
    text = request.form["text"]

    in_path = os.path.join(UPLOAD_FOLDER, image.filename)
    out_path = os.path.join(UPLOAD_FOLDER, "stego_" + image.filename)

    image.save(in_path)
    embed_text(in_path, out_path, text)

    return {"message": "Text embedded successfully"}


@app.route("/extract-text", methods=["POST"])
def extract_plain_text():
    image = request.files["image"]
    path = os.path.join(UPLOAD_FOLDER, image.filename)
    image.save(path)

    text = extract_text(path)
    return {"extracted_text": text}


# =================================================
# AES + TEXT (PASSWORD BASED – TEST STAGE)
# =================================================
@app.route("/embed-encrypted-text", methods=["POST"])
def embed_encrypted_text():
    image = request.files["image"]
    text = request.form["text"]
    password = request.form["password"]

    auth_hash = sha256_hash(password)
    encrypted = aes_encrypt(text, auth_hash)

    in_path = os.path.join(UPLOAD_FOLDER, image.filename)
    out_path = os.path.join(UPLOAD_FOLDER, "secure_" + image.filename)

    image.save(in_path)
    embed_text(in_path, out_path, encrypted)

    return {"message": "Encrypted text embedded successfully"}


@app.route("/extract-encrypted-text", methods=["POST"])
def extract_encrypted_text():
    image = request.files["image"]
    password = request.form["password"]

    path = os.path.join(UPLOAD_FOLDER, image.filename)
    image.save(path)

    encrypted = extract_text(path)
    auth_hash = sha256_hash(password)

    try:
        decrypted = aes_decrypt(encrypted, auth_hash)
        return {"decrypted_text": decrypted}
    except:
        return {"error": "Invalid password"}, 401


# =================================================
# FINAL AUTH SYSTEM – TEXT (QA / KEY)
# =================================================
@app.route("/embed-final-text", methods=["POST"])
def embed_final_text():
    user_id = int(request.form["user_id"])

    # 🔐 CHECK LIMIT
    if get_remaining_attempts(user_id) <= 0:
        return {"error": "Encryption limit exhausted"}, 403

    image = request.files["image"]
    text = request.form["text"]
    encryption_type = request.form["encryption_type"]

    if encryption_type == "QA":
        question = request.form["question"]
        auth_value = request.form["answer"].lower().strip()
    else:
        question = ""
        auth_value = request.form["key"]

    auth_hash = sha256_hash(auth_value)
    encrypted = aes_encrypt(text, auth_hash)

    payload = {
        "encryption_type": encryption_type,
        "payload_type": "TEXT",
        "encrypted_payload": encrypted,
        "question": question,
        "auth_hash": auth_hash
    }

    in_path = os.path.join(UPLOAD_FOLDER, image.filename)
    # 📛 Decide output image name
    output_name = request.form.get("output_name")

    filename = normalize_output_filename(
        output_name,
        image.filename
    )
    base_name = filename
    counter = 1
    out_path = os.path.join(UPLOAD_FOLDER, base_name)

    while os.path.exists(out_path):
        name, ext = os.path.splitext(base_name)
        new_name = f"{name}_{counter}{ext}"
        out_path = os.path.join(UPLOAD_FOLDER, new_name)
        counter += 1

    filename = os.path.basename(out_path)

    image.save(in_path)
    embed_text(in_path, out_path, json.dumps(payload))

    # 🧹 DELETE ORIGINAL IMAGE
    if os.path.exists(in_path):
        os.remove(in_path)


    # 🔐 DECREMENT LIMIT
    decrement_attempt(user_id)
    save_encrypted_image(user_id, out_path)

    return {"message": "Final encrypted text embedded",
    "filename": filename
    }



@app.route("/extract-final-text", methods=["POST"])
def extract_final_text():
    image = request.files["image"]
    user_input = request.form["input"]

    path = os.path.join(UPLOAD_FOLDER, image.filename)
    image.save(path)

    payload = json.loads(extract_text(path))
    input_hash = sha256_hash(user_input)

    if input_hash != payload["auth_hash"]:
        return {"error": "Authentication failed"}, 401

    decrypted = aes_decrypt(payload["encrypted_payload"], input_hash)
    return {"text": decrypted}


# =================================================
# FINAL AUTH SYSTEM – FILE PAYLOAD
# =================================================

@app.route("/embed-final-file", methods=["POST"])
def embed_final_file():
    user_id = int(request.form["user_id"])

    # 🔐 CHECK LIMIT
    if get_remaining_attempts(user_id) <= 0:
        return {"error": "Encryption limit exhausted"}, 403

    image = request.files["image"]
    payload_file = request.files["payload"]
    payload_type = payload_file.filename.split('.')[-1].upper()
    encryption_type = request.form["encryption_type"]

    if encryption_type == "QA":
        question = request.form["question"]
        auth_value = request.form["answer"].lower().strip()
    else:
        question = ""
        auth_value = request.form["key"]

    auth_hash = sha256_hash(auth_value)
    payload_base64 = file_to_base64(payload_file)
    encrypted_payload = aes_encrypt(payload_base64, auth_hash)

    payload = {
        "encryption_type": encryption_type,
        "payload_type": payload_type,
        "encrypted_payload": encrypted_payload,
        "question": question,
        "auth_hash": auth_hash,
        "filename": payload_file.filename
    }

    in_path = os.path.join(UPLOAD_FOLDER, image.filename)
    # 📛 Decide output image name
    output_name = request.form.get("output_name")

    filename = normalize_output_filename(
        output_name,
        image.filename
    )

    base_name = filename
    counter = 1
    out_path = os.path.join(UPLOAD_FOLDER, base_name)

    while os.path.exists(out_path):
        name, ext = os.path.splitext(base_name)
        new_name = f"{name}_{counter}{ext}"
        out_path = os.path.join(UPLOAD_FOLDER, new_name)
        counter += 1

    filename = os.path.basename(out_path)


    image.save(in_path)
    embed_text(in_path, out_path, json.dumps(payload))

    # 🧹 DELETE ORIGINAL IMAGE
    if os.path.exists(in_path):
        os.remove(in_path)

    # 🔐 DECREMENT LIMIT
    decrement_attempt(user_id)
    save_encrypted_image(user_id, out_path)

    return {"message": "File embedded successfully",
    "filename": filename
    }


@app.route("/extract-final-file", methods=["POST"])
def extract_final_file():
    image = request.files["image"]
    user_input = request.form["input"]

    path = os.path.join(UPLOAD_FOLDER, image.filename)
    image.save(path)

    payload = json.loads(extract_text(path))
    input_hash = sha256_hash(user_input)

    if input_hash != payload["auth_hash"]:
        return {"error": "Authentication failed"}, 401

    decrypted_base64 = aes_decrypt(payload["encrypted_payload"], input_hash)
    file_bytes = base64_to_file(decrypted_base64)

    return send_file(
        io.BytesIO(file_bytes),
        download_name=payload["filename"],
        as_attachment=True
    )


# Add to app.py (after existing routes)

@app.route("/download-image/<filename>", methods=["GET"])
def download_image(filename):
    """Download encrypted image from Uploads folder"""
    try:
        return send_file(
            os.path.join(UPLOAD_FOLDER, filename),
            as_attachment=True,
            download_name=filename
        )
    except FileNotFoundError:
        return {"error": "File not found"}, 404

@app.route("/extract-metadata", methods=["POST"])
def extract_metadata():
    """Extract metadata (question/auth mode) from encrypted image"""
    image = request.files["image"]
    path = os.path.join(UPLOAD_FOLDER, image.filename)
    image.save(path)
    
    try:
        extracted = extract_text(path)
        payload = json.loads(extracted)
        
        return {
            "encryption_type": payload.get("encryption_type"),
            "question": payload.get("question", ""),
            "payload_type": payload.get("payload_type")
        }
    except:
        return {"error": "Failed to extract metadata"}, 400

@app.route("/my-uploads", methods=["GET"])
def my_uploads():
    user_id = int(request.args.get("user_id"))
    uploads = get_user_uploads(user_id)
    return {"uploads": uploads}

@app.route("/delete-upload", methods=["POST"])
def delete_upload():
    data = request.json
    user_id = int(data["user_id"])
    upload_id = int(data["upload_id"])

    image_path = delete_user_upload(user_id, upload_id)

    if not image_path:
        return {"error": "Upload not found or unauthorized"}, 404

    # Delete file from disk
    if os.path.exists(image_path):
        os.remove(image_path)

    return {"message": "Upload deleted successfully"}

@app.route("/encryption-limit", methods=["GET"])
def encryption_limit():
    user_id = int(request.args.get("user_id"))
    remaining = get_remaining_attempts(user_id)
    return {"remaining_attempts": remaining}




@app.route("/plans", methods=["GET"])
def get_plans():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name, price, encryptions FROM plans")
    plans = cursor.fetchall()
    conn.close()
    return jsonify({"plans": plans})

@app.route("/create-order", methods=["POST"])
def create_order():
    data = request.json or {}

    user_id = int(data["user_id"])
    plan_id = int(data["plan_id"])

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT price FROM plans WHERE id = %s",
        (plan_id,)
    )
    plan = cursor.fetchone()

    if not plan:
        conn.close()
        return {"error": "Invalid plan"}, 400

    amount = int(plan["price"])  # amount in INR

    order = razorpay_client.order.create({
        "amount": amount * 100,  # convert to paise
        "currency": "INR",
        "payment_capture": 1
    })

    conn.close()

    return {
        "order_id": order["id"],
        "amount": amount,
        "currency": "INR"
    }

@app.route("/verify-payment", methods=["POST"])
def verify_payment():

    data = request.json or {}

    user_id = data.get("user_id")
    plan_id = data.get("plan_id")
    order_id = data.get("order_id")
    payment_id = data.get("payment_id")

    if not user_id or not plan_id or not order_id or not payment_id:
        return {"error": "Missing payment data"}, 400

    user_id = int(user_id)
    plan_id = int(plan_id)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
    "SELECT price, encryptions FROM plans WHERE id = %s",
    (plan_id,)
    )
    plan = cursor.fetchone()

    if not plan:
        conn.close()
        return {"error": "Invalid plan"}, 400


    encryptions_to_add = int(plan["encryptions"])

    cursor.execute(
        "SELECT remaining_attempts FROM encryption_limits WHERE user_id=%s",
        (user_id,)
    )
    row = cursor.fetchone()

    if row:
        cursor.execute(
            "UPDATE encryption_limits SET remaining_attempts = remaining_attempts + %s WHERE user_id=%s",
            (encryptions_to_add, user_id)
        )
    else:
        cursor.execute(
            "INSERT INTO encryption_limits (user_id, remaining_attempts) VALUES (%s, %s)",
            (user_id, encryptions_to_add)
        )

    # Store payment record with plan_id
    cursor.execute(
    """
    INSERT INTO payments (user_id, payment_id, amount, status, plan_id)
    VALUES (%s, %s, %s, %s, %s)
    """,
    (
        user_id,
        payment_id,
        plan["price"],   # actual ₹ amount
        "SUCCESS",
        plan_id
    )
    )


    conn.commit()
    conn.close()

    return {
        "message": "Payment verified and encryption limit increased",
        "added_encryptions": encryptions_to_add
    }

# Add this after the /verify-payment route (around line 450)
@app.route("/user/payments", methods=["GET"])
def user_payments():
    """Get payment history for a specific user"""
    user_id = int(request.args.get("user_id"))
    
    if not user_id:
        return {"error": "User ID required"}, 400
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT 
            p.id,
            p.amount,
            p.status,
            p.created_at,
            p.payment_id,
            pl.name AS plan_name,
            pl.encryptions
        FROM payments p
        JOIN plans pl ON p.plan_id = pl.id
        WHERE p.user_id = %s
        ORDER BY p.created_at DESC
    """, (user_id,))
    
    payments = cursor.fetchall()
    conn.close()
    
    # Format dates for better display
    for payment in payments:
        if payment['created_at']:
            payment['created_at'] = payment['created_at'].strftime('%Y-%m-%d %H:%M:%S')
    
    return {"payments": payments}

@app.route("/user-email", methods=["GET"])
def get_user_email():
    user_id = int(request.args.get("user_id"))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT email FROM users WHERE id = %s",
        (user_id,)
    )
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return {"email": user["email"]}
    return {"error": "User not found"}, 404

if __name__ == "__main__":
    app.run(debug=True)


