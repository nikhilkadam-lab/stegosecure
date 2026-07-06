from cryptography.fernet import Fernet
import base64

def aes_encrypt(data: str, key_hash: str) -> str:
    key = base64.urlsafe_b64encode(bytes.fromhex(key_hash))
    fernet = Fernet(key)
    return fernet.encrypt(data.encode()).decode()

def aes_decrypt(cipher_text: str, key_hash: str) -> str:
    key = base64.urlsafe_b64encode(bytes.fromhex(key_hash))
    fernet = Fernet(key)
    return fernet.decrypt(cipher_text.encode()).decode()
