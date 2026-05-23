import base64
from django.conf import settings
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_fernet = None

def _get_fernet():
    global _fernet
    if _fernet is None:
        # Derive a key from django settings.SECRET_KEY
        salt = b"openoutreach_salt"  # static salt is fine since SECRET_KEY is high entropy/secret
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(settings.SECRET_KEY.encode("utf-8")))
        _fernet = Fernet(key)
    return _fernet

def is_encrypted(value: str) -> bool:
    if not isinstance(value, str):
        return False
    return value.startswith("gAAAA")

def encrypt_value(value: str) -> str:
    if not value:
        return ""
    if is_encrypted(value):
        return value
    f = _get_fernet()
    return f.encrypt(value.encode("utf-8")).decode("utf-8")

def decrypt_value(value: str) -> str:
    if not value:
        return ""
    if not is_encrypted(value):
        return value
    f = _get_fernet()
    try:
        return f.decrypt(value.encode("utf-8")).decode("utf-8")
    except Exception:
        # Fallback to returning the value as-is if decryption fails
        return value
