"""
NEXUS — Auth security helpers: password hashing and JWT issuance/verification.
"""
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def _normalize_answer(answer: str) -> str:
    # Security-question answers shouldn't fail a legitimate user over
    # capitalization or stray whitespace ("Paris" vs "paris "), so both
    # hashing and verification normalize the same way first.
    return answer.strip().lower()


def hash_security_answer(answer: str) -> str:
    return pwd_context.hash(_normalize_answer(answer))


def verify_security_answer(answer: str, answer_hash: str) -> bool:
    return pwd_context.verify(_normalize_answer(answer), answer_hash)


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except JWTError:
        return None
