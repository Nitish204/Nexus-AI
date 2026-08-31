"""NEXUS — Web Push subscription management for the installed PWA."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.db.models import PushSubscription
from app.db.session import get_session
from app.api.projects import get_current_user_id

settings = get_settings()
router = APIRouter(prefix="/api/push", tags=["push"])


class SubscribeRequest(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


@router.get("/vapid-public-key")
async def get_vapid_public_key():
    if not settings.vapid_public_key:
        raise HTTPException(503, "Push notifications aren't configured on this server.")
    return {"public_key": settings.vapid_public_key}


@router.post("/subscribe")
async def subscribe(
    body: SubscribeRequest,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    existing = (
        await session.exec(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    ).first()
    if existing:
        existing.user_id = user_id
        existing.p256dh = body.p256dh
        existing.auth = body.auth
        session.add(existing)
        await session.commit()
        return {"status": "updated"}

    sub = PushSubscription(user_id=user_id, endpoint=body.endpoint, p256dh=body.p256dh, auth=body.auth)
    session.add(sub)
    await session.commit()
    return {"status": "subscribed"}


@router.post("/unsubscribe")
async def unsubscribe(
    body: SubscribeRequest,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    existing = (
        await session.exec(
            select(PushSubscription).where(
                PushSubscription.endpoint == body.endpoint, PushSubscription.user_id == user_id
            )
        )
    ).first()
    if existing:
        await session.delete(existing)
        await session.commit()
    return {"status": "unsubscribed"}
