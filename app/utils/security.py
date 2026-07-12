import base64
import hashlib
import secrets
from typing import Optional

_ITERATIONS = 390000


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password cannot be empty")

    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _ITERATIONS,
    )
    salt_b64 = base64.b64encode(salt).decode("ascii")
    hash_b64 = base64.b64encode(derived).decode("ascii")
    return f"pbkdf2_sha256${_ITERATIONS}${salt_b64}${hash_b64}"


def verify_password(plain_password: str, stored_password: Optional[str]) -> bool:
    if not plain_password or not stored_password:
        return False

    if stored_password.startswith("pbkdf2_sha256$"):
        try:
            _, iterations_str, salt_b64, hash_b64 = stored_password.split("$", 3)
            iterations = int(iterations_str)
            salt = base64.b64decode(salt_b64.encode("ascii"))
            expected_hash = base64.b64decode(hash_b64.encode("ascii"))
            derived = hashlib.pbkdf2_hmac(
                "sha256",
                plain_password.encode("utf-8"),
                salt,
                iterations,
            )
            return hashlib.compare_digest(derived, expected_hash)
        except Exception:
            return False

    return stored_password == plain_password
