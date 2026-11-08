import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from app.core.security import LEGACY_DEFAULT_SECRET, SECRET_KEY
from app.models.domain import User

def _get_user_derived_key(user: User, secret: str = None) -> bytes:
    """
    Derives a unique encryption key for the user using their hashed_password as salt.
    This ensures each user's API key is encrypted with a unique key.
    """
    salt = user.hashed_password.encode('utf-8')[:16] # Use part of hashed password as salt
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend()
    )
    key = base64.urlsafe_b64encode(kdf.derive((secret or SECRET_KEY).encode('utf-8')))
    return key

def encrypt_api_key(api_key: str, user: User) -> str:
    if not api_key:
        return None
    key = _get_user_derived_key(user)
    f = Fernet(key)
    return f.encrypt(api_key.encode('utf-8')).decode('utf-8')

def decrypt_api_key(encrypted_key: str, user: User) -> str:
    if not encrypted_key:
        return None
    # ลองด้วย secret ปัจจุบันก่อน แล้วค่อย fallback ไปค่า default เดิม — key ที่บันทึกไว้ก่อนแก้ไข
    # การอ่าน SECRET_KEY (ดู app/core/security.py) ถูกเข้ารหัสด้วยค่า default เดิม ผู้ใช้จึงยังใช้ได้ต่อ
    # (บันทึก key ใหม่อีกครั้งเมื่อไรจะถูกเข้ารหัสด้วย secret ปัจจุบันเอง)
    for secret in (SECRET_KEY, LEGACY_DEFAULT_SECRET):
        try:
            f = Fernet(_get_user_derived_key(user, secret))
            return f.decrypt(encrypted_key.encode('utf-8')).decode('utf-8')
        except Exception:
            continue
    return None
