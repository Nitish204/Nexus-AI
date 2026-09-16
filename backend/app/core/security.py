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

import pyotp
from jose import jwt, JWTError
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt_sha256", "bcrypt"], deprecated="auto")

# Separate from the main access token's expiry — this is intentionally
# short, since it only exists for the few seconds between "password was
# correct" and "user typed their 6-digit code", not as a real session.
TWO_FA_PENDING_TOKEN_MINUTES = 5


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
    # `jti` (JWT ID) — a unique identifier for THIS specific token, not
    # the user. Needed so logout can revoke exactly one session without
    # affecting any of the user's other logged-in devices/browsers, and
    # so the revoked-list only ever needs to remember "this one token",
    # not "this user's tokens" (which would require tracking every
    # token ever issued to look them up later).
    payload = {"sub": user_id, "exp": expire, "jti": secrets.token_urlsafe(16)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    """
    Returns the full decoded payload ({"sub", "exp", "jti"}) rather than
    just the user id, so callers can check the token's jti against the
    revocation list (see app/core/token_revocation.py) — a token that's
    cryptographically valid and unexpired can still have been explicitly
    logged out early, and callers need the jti to check that.
    """
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------------
# Two-factor auth (TOTP)
# ---------------------------------------------------------------------

def generate_totp_secret() -> str:
    return pyotp.random_base32()


def totp_provisioning_uri(secret: str, email: str) -> str:
    """The otpauth:// URI an authenticator app (Google Authenticator,
    1Password, Authy, etc.) scans as a QR code or accepts as manual
    entry. Rendering it as an actual QR image is left to the frontend —
    keeps this backend free of an image-generation dependency for
    something the browser can do cheaply itself from this URI alone."""
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="Nexus")


def verify_totp_code(secret: str, code: str) -> bool:
    # valid_window=1 accepts the current 30-second step plus one step
    # on either side (~±30s of clock drift) — without this, a phone or
    # server clock that's even slightly out of sync produces constant,
    # confusing "invalid code" failures on codes that are actually
    # correct. Wider than 1 would start meaningfully weakening the
    # 6-digit code's effective guess-space, so this isn't just bumped
    # up further "to be safe".
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def generate_backup_codes(count: int = 10) -> list[str]:
    """Plaintext codes shown to the user exactly once, at generation
    time. Only their hashes are ever stored (see hash_backup_code) —
    same principle as passwords: the server should never be able to
    show these again either, only verify a guess against them."""
    return ["-".join([secrets.token_hex(2), secrets.token_hex(2)]) for _ in range(count)]


def hash_backup_code(code: str) -> str:
    return pwd_context.hash(code.strip().lower())


def verify_backup_code(code: str, code_hash: str) -> bool:
    return pwd_context.verify(code.strip().lower(), code_hash)


def create_2fa_pending_token(user_id: str) -> str:
    """
    Issued right after a password check succeeds for an account with
    2FA enabled — proves "this request knows the correct password" but
    deliberately cannot be used as a real session token. Two things
    enforce that separation: a `purpose` claim that get_current_user_id
    explicitly rejects (see api/projects.py) even if someone tried
    passing this as a normal Bearer token, and the short
    TWO_FA_PENDING_TOKEN_MINUTES expiry. It also carries no `jti` and is
    never written to the revocation list — it isn't a session, so there
    is nothing there to revoke; logging out doesn't need to know it
    exists.
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=TWO_FA_PENDING_TOKEN_MINUTES)
    payload = {"sub": user_id, "exp": expire, "purpose": "2fa_pending"}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_2fa_pending_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    if payload.get("purpose") != "2fa_pending":
        return None
    return payload.get("sub")
