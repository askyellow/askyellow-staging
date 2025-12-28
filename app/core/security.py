# core/security.py

from passlib.context import CryptContext

pwd_context = CryptContext(
    schemes=["bcrypt_sha256", "scrypt"],
    deprecated="auto"
)

def normalize_password(password: str) -> str:
    if not password:
        return ""
    return password.strip()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)
