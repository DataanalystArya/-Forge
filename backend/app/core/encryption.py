import base64
import hashlib
from cryptography.fernet import Fernet
from app.core.config import settings


def _get_fernet() -> Fernet:
    """Derive a consistent 32-byte Fernet key from SECRET_KEY."""
    derived_key = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    url_safe_key = base64.urlsafe_b64encode(derived_key)
    return Fernet(url_safe_key)


def encrypt_token(plain_token: str) -> str:
    """Encrypt a plaintext secret token for secure at-rest storage."""
    if not plain_token:
        return ""
    f = _get_fernet()
    encrypted_bytes = f.encrypt(plain_token.encode("utf-8"))
    return encrypted_bytes.decode("utf-8")


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt a secret token from storage."""
    if not encrypted_token:
        return ""
    try:
        f = _get_fernet()
        decrypted_bytes = f.decrypt(encrypted_token.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except Exception:
        return ""
