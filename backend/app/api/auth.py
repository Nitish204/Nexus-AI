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
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, field_validator
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.rate_limit import enforce, login_limiter, security_answer_limiter, signup_limiter
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_csrf_token,
    hash_password,
    hash_security_answer,
    verify_password,
    verify_security_answer,
)
from app.db.models import AuthProvider, User
from app.db.session import get_session

settings = get_settings()
router = APIRouter(prefix="/api/auth", tags=["auth"])

MIN_PASSWORD_LENGTH = 8
SESSION_COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 days
WS_TOKEN_MINUTES = 5


def _validate_password_strength(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    return password


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    name: str = ""
    security_question: str
    security_answer: str

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleLoginRequest(BaseModel):
    id_token: str


class GitHubLoginRequest(BaseModel):
    code: str


class DirectResetPasswordRequest(BaseModel):
    email: EmailStr
    security_answer: str
    new_password: str

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
    enforce(signup_limiter, request)
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
    enforce(login_limiter, request, extra_key=body.email.lower())
    user = (await session.exec(select(User).where(User.email == body.email))).first()
    if not user:
        raise HTTPException(401, "Invalid email or password.")
    if not user.password_hash:
        raise HTTPException(
            401,
            "This account was created with Google or GitHub and has no password yet. "
            "Use 'Forgot password?' to set one, or continue with Google/GitHub.",
        )
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password.")
    result = _issue(user)
    _set_session_cookies(response, result["access_token"])
    return result


@router.post("/logout")
async def logout(response: Response):
    _clear_session_cookies(response)
    return {"status": "logged_out"}


@router.get("/security-question")
async def get_security_question(email: EmailStr, request: Request, session: AsyncSession = Depends(get_session)):
    enforce(security_answer_limiter, request, extra_key="enum")
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
    enforce(security_answer_limiter, request, extra_key=body.email.lower())
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
    enforce(login_limiter, request, extra_key="google")
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
    enforce(login_limiter, request, extra_key="github")
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
    result = _issue(user)
    _set_session_cookies(response, result["access_token"])
    return result


def _resolve_user_id(request: Request, authorization: str | None) -> str:
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
    else:
        token = request.cookies.get("nexus_session")
    if not token:
        raise HTTPException(401, "Missing authentication.")
    user_id = decode_access_token(token)
    if not user_id:
        raise HTTPException(401, "Invalid or expired token.")
    return user_id


@router.get("/me")
async def get_me(
    request: Request, authorization: str | None = Header(default=None), session: AsyncSession = Depends(get_session)
):
    user_id = _resolve_user_id(request, authorization)
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(401, "User not found.")
    return {"id": user.id, "email": user.email, "name": user.name, "avatar_url": user.avatar_url}


@router.get("/ws-token")
async def get_ws_token(request: Request, authorization: str | None = Header(default=None)):
    user_id = _resolve_user_id(request, authorization)
    return {"ws_token": create_access_token(user_id, expires_minutes=WS_TOKEN_MINUTES)}
