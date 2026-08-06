"""
NEXUS — Authentication routes: email/password signup+login, Google
Sign-In (ID token verification), and GitHub OAuth (code exchange).
"""
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_reset_token,
    decode_access_token,
    decode_reset_token,
    hash_password,
    verify_password,
)
from app.db.models import AuthProvider, User
from app.db.session import get_session

settings = get_settings()
router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: str
    password: str
    name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class GoogleLoginRequest(BaseModel):
    id_token: str


class GitHubLoginRequest(BaseModel):
    code: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


def _issue(user: User) -> dict:
    return {
        "access_token": create_access_token(user.id),
        "user": {"id": user.id, "email": user.email, "name": user.name, "avatar_url": user.avatar_url},
    }


@router.post("/signup")
async def signup(body: SignupRequest, session: AsyncSession = Depends(get_session)):
    existing = (await session.exec(select(User).where(User.email == body.email))).first()
    if existing:
        raise HTTPException(400, "An account with this email already exists.")
    user = User(
        email=body.email,
        name=body.name or body.email.split("@")[0],
        password_hash=hash_password(body.password),
        provider=AuthProvider.LOCAL,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return _issue(user)


@router.post("/login")
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    user = (await session.exec(select(User).where(User.email == body.email))).first()
    if not user:
        raise HTTPException(401, "Invalid email or password.")
    if not user.password_hash:
        # Account exists but was created via Google/GitHub, so there's
        # nothing to check a typed password against yet — this is the
        # single most common cause of "invalid password" confusion, so
        # it gets its own message instead of the generic one.
        raise HTTPException(
            401,
            "This account was created with Google or GitHub and has no password yet. "
            "Use 'Forgot password?' to set one, or continue with Google/GitHub.",
        )
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password.")
    return _issue(user)


def _send_reset_email(email: str, reset_link: str) -> None:
    """
    No SMTP/email provider is configured yet, so this just logs the
    link server-side. Wire in a real provider (SES, SendGrid, Postmark,
    etc.) here — the rest of the flow (token creation/verification,
    endpoints, frontend screen) doesn't need to change when you do.
    """
    print(f"[password reset] {email} -> {reset_link}")


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, session: AsyncSession = Depends(get_session)):
    user = (await session.exec(select(User).where(User.email == body.email))).first()
    # Always return the same response whether or not the account exists,
    # so this endpoint can't be used to test which emails are registered.
    generic_response = {"message": "If an account exists for that email, a reset link has been sent."}
    if not user:
        return generic_response

    token = create_reset_token(user.id)
    reset_link = f"{settings.frontend_base_url}/reset-password?token={token}"
    _send_reset_email(user.email, reset_link)

    if settings.environment == "development":
        # Surfaced directly so the flow is testable with no email
        # provider configured — remove this field once real email
        # sending is wired up in _send_reset_email above.
        generic_response["dev_reset_token"] = token
    return generic_response


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, session: AsyncSession = Depends(get_session)):
    user_id = decode_reset_token(body.token)
    if not user_id:
        raise HTTPException(400, "This reset link is invalid or has expired. Please request a new one.")
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(400, "This reset link is invalid or has expired. Please request a new one.")
    if len(body.new_password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")

    user.password_hash = hash_password(body.new_password)
    session.add(user)
    await session.commit()
    return {"message": "Password updated. You can now sign in with your new password."}


@router.post("/google")
async def google_login(body: GoogleLoginRequest, session: AsyncSession = Depends(get_session)):
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://oauth2.googleapis.com/tokeninfo", params={"id_token": body.id_token}
        )
    if resp.status_code != 200:
        raise HTTPException(401, "Invalid Google token.")
    data = resp.json()
    if data.get("aud") != settings.google_client_id:
        raise HTTPException(401, "Google token was not issued for this app.")

    email = data["email"]
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
    return _issue(user)


@router.post("/github")
async def github_login(body: GitHubLoginRequest, session: AsyncSession = Depends(get_session)):
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
    return _issue(user)


@router.get("/me")
async def get_me(token: str, session: AsyncSession = Depends(get_session)):
    user_id = decode_access_token(token)
    if not user_id:
        raise HTTPException(401, "Invalid or expired token.")
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(401, "User not found.")
    return {"id": user.id, "email": user.email, "name": user.name, "avatar_url": user.avatar_url}
