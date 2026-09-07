"""
NEXUS — Auth security helpers: password hashing and JWT issuance/verification.

Fix vs. the original version: the passlib context used the plain
"bcrypt" scheme, which silently truncates any input past 72 bytes.
That means two different passwords that share the same first 72 bytes
hash identically, and — more visibly — anyone using a long passphrase
gets truncated on signup but may retype it differently (still >72
bytes) on login and see a confusing "invalid password" even though
what they typed is "correct". "bcrypt_sha256" pre-hashes the input
with SHA-256 before handing it to bcrypt, removing the length cap
entirely while staying within the same battle-tested bcrypt work
factor. `deprecated="auto"` means any password hashed under the old
"bcrypt" scheme (from before this fix) will still verify correctly and
gets transparently re-hashed under the new scheme on next login.
"""
from datetime import datetime, timedelta, timezone
import secrets

from jose import jwt, JWTError
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt_sha256", "bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def _normalize_answer(answer: str) -> str:
    return answer.strip().lower()


def hash_security_answer(answer: str) -> str:
    return pwd_context.hash(_normalize_answer(answer))


def verify_security_answer(answer: str, answer_hash: str) -> bool:
    return pwd_context.verify(_normalize_answer(answer), answer_hash)


def create_access_token(user_id: str, expires_minutes: int | None = None) -> str:
    minutes = expires_minutes if expires_minutes is not None else settings.access_token_expire_minutes
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except JWTError:
        return None


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)
