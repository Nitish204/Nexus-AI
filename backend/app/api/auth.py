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
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
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
    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password.")
    return _issue(user)


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
