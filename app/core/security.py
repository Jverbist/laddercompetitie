import base64
import hashlib
import hmac
import os


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived_key = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${base64.b64encode(salt).decode()}${base64.b64encode(derived_key).decode()}"


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        algorithm, encoded_salt, encoded_key = password_hash.split("$", maxsplit=2)
        if algorithm != "scrypt":
            return False
        salt = base64.b64decode(encoded_salt)
        expected_key = base64.b64decode(encoded_key)
    except (ValueError, UnicodeDecodeError):
        return False

    actual_key = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return hmac.compare_digest(actual_key, expected_key)
