"""
NEXUS — Authentication routes: email/password signup+login, Google
Sign-In (ID token verification), and GitHub OAuth (code exchange).

Session model: the web app authenticates via an httpOnly cookie set by
this file (JS on the page can never read it, closing off token theft
via any future XSS bug elsewhere in the app). The mobile app — which
has no cookie jar shared with a browser and a different threat model —
continues to receive the token in the response body and send it back
as a Bearer header, exactly as before. Both paths are accepted by
`get_current_user_id` in api/projects.py.
"""
import httpx
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, field_validator
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.rate_limit import enforce, login_limiter, security_answer_limiter, signup_limiter, totp_limiter
from app.core.token_revocation import revoke_token, is_token_revoked
from app.api.projects import _validate_session_payload, get_current_user_id
from app.core.security import (
    api_key_lookup_prefix,
    create_access_token,
    create_2fa_pending_token,
    decode_2fa_pending_token,
    decode_access_token,
    generate_api_key,
    generate_backup_codes,
    generate_csrf_token,
    generate_totp_secret,
    hash_api_key,
    hash_backup_code,
    hash_password,
    hash_security_answer,
    totp_provisioning_uri,
    verify_backup_code,
    verify_password,
    verify_security_answer,
    verify_totp_code,
)
from app.db.models import ApiKey, AuthProvider, User
from app.db.session import get_session
from app.services.push_notifications import send_push_to_user

logger = logging.getLogger("nexus.auth")

settings = get_settings()
router = APIRouter(prefix="/api/auth", tags=["auth"])

# 10 total wrong guesses (not per-window like the rate limiter — this
# accumulates until a successful login resets it) before the account
# itself locks, regardless of which IP(s) the guesses came from. 30
# minutes is deliberately long enough to be a real deterrent against
# automated guessing but short enough that a genuine user who mistyped
# their password several times isn't locked out for the whole day.
ACCOUNT_LOCKOUT_THRESHOLD = 10
ACCOUNT_LOCKOUT_MINUTES = 30

MIN_PASSWORD_LENGTH = 8
SESSION_COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 days
WS_TOKEN_MINUTES = 5


def _validate_password_strength(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    return password


def _normalize_email(v: str) -> str:
    """
    Every email read or write in this file now goes through this.
    Previously, nothing normalized case: Postgres text comparison is
    case-sensitive by default, so `Bob@Gmail.com` at signup and
    `bob@gmail.com` at login were treated as two different values
    entirely. That meant a correct password could still get "Invalid
    email or password" purely from a casing mismatch, the "account
    already exists" signup check could be bypassed by varying case, and
    worst of all: someone who signed up locally as `Bob@Gmail.com` and
    later used "Sign in with Google" (which returns lowercase) would
    silently get a brand-new, second account instead of their existing
    one — Google/GitHub OAuth and password login could never find each
    other's accounts for the same real email.
    """
    return v.strip().lower()


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    name: str = ""
    security_question: str
    security_answer: str

    @field_validator("email")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return _normalize_email(v)

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return _normalize_email(v)


class GoogleLoginRequest(BaseModel):
    id_token: str


class GitHubLoginRequest(BaseModel):
    code: str


class DirectResetPasswordRequest(BaseModel):
    email: EmailStr
    security_answer: str
    new_password: str

    @field_validator("email")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return _normalize_email(v)

    @field_validator("new_password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)


def _set_session_cookies(response: Response, access_token: str) -> None:
    is_prod = settings.environment == "production"
    same_site = "none" if is_prod else "lax"
    secure = is_prod

    response.set_cookie(
        "nexus_session", access_token, httponly=True, secure=secure,
        samesite=same_site, max_age=SESSION_COOKIE_MAX_AGE, path="/",
    )
    response.set_cookie(
        "nexus_csrf", generate_csrf_token(), httponly=False, secure=secure,
        samesite=same_site, max_age=SESSION_COOKIE_MAX_AGE, path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie("nexus_session", path="/")
    response.delete_cookie("nexus_csrf", path="/")


def _issue(user: User) -> dict:
    return {
        "access_token": create_access_token(user.id),
        "user": {"id": user.id, "email": user.email, "name": user.name, "avatar_url": user.avatar_url},
    }


@router.post("/signup")
async def signup(
    request: Request, response: Response, body: SignupRequest, session: AsyncSession = Depends(get_session)
):
    await enforce(signup_limiter, request)
    existing = (await session.exec(select(User).where(User.email == body.email))).first()
    if existing:
        raise HTTPException(400, "An account with this email already exists.")
    user = User(
        email=body.email,
        name=body.name or body.email.split("@")[0],
        password_hash=hash_password(body.password),
        provider=AuthProvider.LOCAL,
        security_question=body.security_question,
        security_answer_hash=hash_security_answer(body.security_answer),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    result = _issue(user)
    _set_session_cookies(response, result["access_token"])
    return result


@router.post("/login")
async def login(
    request: Request, response: Response, body: LoginRequest, session: AsyncSession = Depends(get_session)
):
    await enforce(login_limiter, request, extra_key=body.email.lower())
    user = (await session.exec(select(User).where(User.email == body.email))).first()
    if not user:
        raise HTTPException(401, "Invalid email or password.")
    if not user.password_hash:
        raise HTTPException(
            401,
            "This account was created with Google or GitHub and has no password yet. "
            "Use 'Forgot password?' to set one, or continue with Google/GitHub.",
        )

    # Checked BEFORE verifying the password on purpose: once an account
    # is locked, even a genuinely correct password must not succeed
    # until the lockout expires. This is the actual behavioral
    # difference from rate limiting (which only slows down attempt
    # speed, not this specific already-authenticated-looking request).
    now = datetime.now(timezone.utc)
    locked_until = user.locked_until
    if locked_until is not None and locked_until.tzinfo is None:
        # SQLite has no native timezone-aware timestamp type at all —
        # DateTime(timezone=True) is effectively a no-op there, and a
        # value written as UTC-aware comes back naive on round-trip
        # regardless of the column declaration (confirmed directly:
        # this is not a hypothetical). Production Postgres genuinely
        # preserves the timezone, but normalizing here defensively —
        # rather than assuming the driver always behaves — means this
        # can never crash with "can't compare offset-naive and
        # offset-aware datetimes" on every single login attempt for a
        # locked account, in any environment, for any reason. Every
        # value this app ever writes to this column is already UTC
        # (see `now` above), so treating a naive read-back as UTC is
        # correct, not a guess.
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    if locked_until and locked_until > now:
        minutes_left = max(1, int((locked_until - now).total_seconds() // 60) + 1)
        raise HTTPException(
            423,  # 423 Locked — the correct status for "the resource itself is locked", distinct from 401
            f"This account is temporarily locked after repeated failed sign-in attempts. "
            f"Try again in about {minutes_left} minute(s).",
        )

    if not verify_password(body.password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= ACCOUNT_LOCKOUT_THRESHOLD:
            user.locked_until = now + timedelta(minutes=ACCOUNT_LOCKOUT_MINUTES)
            # Reset the counter once locked — the next block of attempts
            # (after the lockout expires) starts counting fresh, rather
            # than the lock re-triggering instantly on the very next
            # single wrong guess.
            user.failed_login_count = 0
        session.add(user)
        await session.commit()

        if user.locked_until:
            # Best-effort — only reaches a device where the user
            # previously granted push permission (see the module
            # docstring on send_push_to_user for the trade-off vs.
            # email). Lockout itself has already happened and doesn't
            # depend on this succeeding; a failed/skipped notification
            # here must never block or fail the login response itself.
            try:
                await send_push_to_user(
                    session, user.id, "Account locked",
                    f"Your Nexus account was locked for {ACCOUNT_LOCKOUT_MINUTES} minutes after "
                    f"{ACCOUNT_LOCKOUT_THRESHOLD} failed sign-in attempts. If this wasn't you, "
                    f"consider changing your password once it unlocks.",
                    url="/settings/security",
                )
            except Exception as exc:
                logger.warning("Failed to send account-lockout push alert for user %s: %s", user.id, exc)
        raise HTTPException(401, "Invalid email or password.")

    if user.failed_login_count > 0 or user.locked_until:
        user.failed_login_count = 0
        user.locked_until = None
        session.add(user)
        await session.commit()

    if user.totp_enabled:
        # Password was correct, but that alone isn't a completed login
        # for a 2FA account. Issue only the short-lived pending token —
        # see create_2fa_pending_token's docstring for why this can
        # never be mistaken for (or used as) a real session — and make
        # the client call /2fa/verify next with the user's 6-digit code.
        return {"requires_2fa": True, "pending_token": create_2fa_pending_token(user.id)}

    result = _issue(user)
    _set_session_cookies(response, result["access_token"])
    return result


@router.post("/logout")
async def logout(request: Request, response: Response, authorization: str | None = Header(default=None)):
    # Actually revoke the current token, not just delete the cookie —
    # see app/core/token_revocation.py for why that distinction matters.
    # Same dual bearer-header/cookie handling as get_current_user_id in
    # api/projects.py, since logout needs to find the same token that
    # would've authenticated this request either way.
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
    else:
        token = request.cookies.get("nexus_session")

    if token:
        payload = decode_access_token(token)
        if payload and payload.get("jti"):
            remaining_seconds = int(payload["exp"] - time.time())
            await revoke_token(payload["jti"], remaining_seconds)

    _clear_session_cookies(response)
    return {"status": "logged_out"}


# ---------------------------------------------------------------------
# Two-factor auth (TOTP)
# ---------------------------------------------------------------------

class TwoFAEnableRequest(BaseModel):
    code: str


class TwoFADisableRequest(BaseModel):
    password: str


class TwoFAVerifyRequest(BaseModel):
    pending_token: str
    code: str


@router.post("/2fa/setup")
async def setup_2fa(user_id: str = Depends(get_current_user_id), session: AsyncSession = Depends(get_session)):
    """
    Generates a new secret and backup codes, but does NOT enable 2FA
    yet — see POST /2fa/enable, which requires proving the authenticator
    app was actually configured correctly first. Calling this again
    before enabling simply replaces the pending secret/codes; calling
    it on an account that already has 2FA enabled starts a fresh
    setup that only takes effect once /2fa/enable is called again,
    without disabling the currently-active 2FA in the meantime.
    """
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found.")

    secret = generate_totp_secret()
    backup_codes = generate_backup_codes()

    user.totp_secret = secret
    user.totp_backup_codes = json.dumps([hash_backup_code(c) for c in backup_codes])
    session.add(user)
    await session.commit()

    return {
        "secret": secret,
        "provisioning_uri": totp_provisioning_uri(secret, user.email),
        # Shown exactly once — only hashes are stored from here on.
        "backup_codes": backup_codes,
    }


@router.post("/2fa/enable")
async def enable_2fa(
    request: Request,
    body: TwoFAEnableRequest,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    await enforce(totp_limiter, request, extra_key=user_id)
    user = await session.get(User, user_id)
    if not user or not user.totp_secret:
        raise HTTPException(400, "Call /2fa/setup first.")
    if not verify_totp_code(user.totp_secret, body.code):
        raise HTTPException(401, "Incorrect code. Check your authenticator app and try again.")

    user.totp_enabled = True
    session.add(user)
    await session.commit()
    return {"status": "2fa_enabled"}


@router.post("/2fa/disable")
async def disable_2fa(
    body: TwoFADisableRequest,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found.")
    if not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Incorrect password.")

    user.totp_enabled = False
    user.totp_secret = None
    user.totp_backup_codes = None
    session.add(user)
    await session.commit()
    return {"status": "2fa_disabled"}


@router.post("/2fa/verify")
async def verify_2fa(
    request: Request, response: Response, body: TwoFAVerifyRequest, session: AsyncSession = Depends(get_session)
):
    """Completes a login that /login paused for 2FA. Accepts either a
    live 6-digit TOTP code or one of the one-time backup codes."""
    user_id = decode_2fa_pending_token(body.pending_token)
    if not user_id:
        raise HTTPException(401, "This login attempt has expired. Please sign in again.")

    await enforce(totp_limiter, request, extra_key=user_id)

    user = await session.get(User, user_id)
    if not user or not user.totp_enabled or not user.totp_secret:
        raise HTTPException(401, "This login attempt has expired. Please sign in again.")

    if verify_totp_code(user.totp_secret, body.code):
        result = _issue(user)
        _set_session_cookies(response, result["access_token"])
        return result

    # Not a valid TOTP code — try it as a one-time backup code instead.
    backup_hashes = json.loads(user.totp_backup_codes) if user.totp_backup_codes else []
    for i, code_hash in enumerate(backup_hashes):
        if verify_backup_code(body.code, code_hash):
            # One-time use: remove it so it can't be replayed.
            del backup_hashes[i]
            user.totp_backup_codes = json.dumps(backup_hashes)
            session.add(user)
            await session.commit()
            result = _issue(user)
            _set_session_cookies(response, result["access_token"])
            return result

    raise HTTPException(401, "Incorrect code.")


# ---------------------------------------------------------------------
# API keys — programmatic access (curl/scripts/CI), no browser session
# ---------------------------------------------------------------------

class CreateApiKeyRequest(BaseModel):
    name: str = "API Key"


@router.post("/api-keys")
async def create_api_key(
    body: CreateApiKeyRequest,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """The raw key is returned ONCE, here, and never again — only its
    hash is stored (see ApiKey.key_hash), the same principle as a
    password. If it's lost, the only recovery is revoking it and
    creating a new one."""
    raw_key = generate_api_key()
    key = ApiKey(
        owner_id=user_id, name=body.name,
        key_hash=hash_api_key(raw_key), key_prefix=api_key_lookup_prefix(raw_key),
    )
    session.add(key)
    await session.commit()
    await session.refresh(key)
    return {"id": key.id, "name": key.name, "key": raw_key, "key_prefix": key.key_prefix, "created_at": key.created_at}


@router.get("/api-keys")
async def list_api_keys(user_id: str = Depends(get_current_user_id), session: AsyncSession = Depends(get_session)):
    result = await session.exec(
        select(ApiKey).where(ApiKey.owner_id == user_id).order_by(ApiKey.created_at.desc())
    )
    return [
        {
            "id": k.id, "name": k.name, "key_prefix": k.key_prefix,
            "created_at": k.created_at, "last_used_at": k.last_used_at, "revoked": k.revoked,
        }
        for k in result.all()
    ]


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: str, user_id: str = Depends(get_current_user_id), session: AsyncSession = Depends(get_session)
):
    key = await session.get(ApiKey, key_id)
    # Same pattern as elsewhere in this file: "doesn't exist" and
    # "exists but isn't yours" get the identical 404, so a request
    # can't be used to probe which key IDs are real.
    if not key or key.owner_id != user_id:
        raise HTTPException(404, "API key not found.")
    key.revoked = True
    session.add(key)
    await session.commit()
    return {"status": "revoked"}


@router.get("/security-question")
async def get_security_question(email: EmailStr, request: Request, session: AsyncSession = Depends(get_session)):
    email = _normalize_email(email)
    await enforce(security_answer_limiter, request, extra_key="enum")
    user = (await session.exec(select(User).where(User.email == email))).first()
    if not user or not user.security_question:
        raise HTTPException(
            404,
            "No security question is set up for that email. If this account was created "
            "with Google or GitHub before security questions existed, sign in that way instead.",
        )
    return {"security_question": user.security_question}


@router.post("/reset-password-direct")
async def reset_password_direct(
    request: Request, body: DirectResetPasswordRequest, session: AsyncSession = Depends(get_session)
):
    await enforce(security_answer_limiter, request, extra_key=body.email.lower())
    user = (await session.exec(select(User).where(User.email == body.email))).first()
    if not user or not user.security_answer_hash:
        raise HTTPException(400, "No security question is set up for that email.")
    if not verify_security_answer(body.security_answer, user.security_answer_hash):
        raise HTTPException(400, "That answer doesn't match. Please try again.")

    user.password_hash = hash_password(body.new_password)
    session.add(user)
    await session.commit()
    return {"message": "Password updated. You can now sign in with your new password."}


@router.post("/google")
async def google_login(
    request: Request, response: Response, body: GoogleLoginRequest, session: AsyncSession = Depends(get_session)
):
    await enforce(login_limiter, request, extra_key="google")
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://oauth2.googleapis.com/tokeninfo", params={"id_token": body.id_token}
        )
    if resp.status_code != 200:
        raise HTTPException(401, "Invalid Google token.")
    data = resp.json()
    if data.get("aud") != settings.google_client_id:
        raise HTTPException(401, "Google token was not issued for this app.")
    if data.get("email_verified") not in ("true", True):
        raise HTTPException(401, "Google account email is not verified.")

    email = data["email"]
    email = _normalize_email(email)
    user = (await session.exec(select(User).where(User.email == email))).first()
    if not user:
        user = User(
            email=email,
            name=data.get("name", email.split("@")[0]),
            provider=AuthProvider.GOOGLE,
            avatar_url=data.get("picture", ""),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    result = _issue(user)
    _set_session_cookies(response, result["access_token"])
    return result


@router.post("/github")
async def github_login(
    request: Request, response: Response, body: GitHubLoginRequest, session: AsyncSession = Depends(get_session)
):
    await enforce(login_limiter, request, extra_key="github")
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": body.code,
            },
        )
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(401, "GitHub code exchange failed.")

        user_resp = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        gh_user = user_resp.json()

        email = gh_user.get("email")
        if not email:
            emails_resp = await client.get(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            emails = emails_resp.json()
            primary = next((e for e in emails if e.get("primary")), emails[0] if emails else None)
            email = primary["email"] if primary else f"{gh_user['login']}@users.noreply.github.com"
        email = _normalize_email(email)

    user = (await session.exec(select(User).where(User.email == email))).first()
    if not user:
        user = User(
            email=email,
            name=gh_user.get("name") or gh_user.get("login", ""),
            provider=AuthProvider.GITHUB,
            avatar_url=gh_user.get("avatar_url", ""),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    result = _issue(user)
    _set_session_cookies(response, result["access_token"])
    return result


async def _resolve_user_id(request: Request, authorization: str | None) -> str:
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
    else:
        token = request.cookies.get("nexus_session")
    if not token:
        raise HTTPException(401, "Missing authentication.")
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(401, "Invalid or expired token.")
    return await _validate_session_payload(payload)


@router.get("/me")
async def get_me(
    request: Request, authorization: str | None = Header(default=None), session: AsyncSession = Depends(get_session)
):
    user_id = await _resolve_user_id(request, authorization)
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(401, "User not found.")
    return {"id": user.id, "email": user.email, "name": user.name, "avatar_url": user.avatar_url}


@router.get("/ws-token")
async def get_ws_token(request: Request, authorization: str | None = Header(default=None)):
    user_id = await _resolve_user_id(request, authorization)
    return {"ws_token": create_access_token(user_id, expires_minutes=WS_TOKEN_MINUTES)}
