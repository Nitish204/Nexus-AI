"""
NEXUS — Web Push notifications for the installed PWA.
"""
from __future__ import annotations

import asyncio
import json
import logging

from pywebpush import webpush, WebPushException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.db.models import Project, PushSubscription

settings = get_settings()
logger = logging.getLogger("nexus.push")


def _send_one(payload: str, sub: PushSubscription) -> None:
    """The actual blocking network call, run off the event loop (see below)."""
    webpush(
        subscription_info={
            "endpoint": sub.endpoint,
            "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
        },
        data=payload,
        vapid_private_key=settings.vapid_private_key,
        vapid_claims={"sub": settings.vapid_subject},
    )


async def send_push_to_project_owner(
    session: AsyncSession, project_id: str, title: str, body: str, url: str = "/"
) -> None:
    if not settings.vapid_private_key or not settings.vapid_public_key:
        return

    project = await session.get(Project, project_id)
    if not project:
        return

    result = await session.exec(
        select(PushSubscription).where(PushSubscription.user_id == project.owner_id)
    )
    subscriptions = result.all()
    if not subscriptions:
        return

    payload = json.dumps({"title": title, "body": body, "url": url})

    # Bug fix: `webpush()` makes a real synchronous HTTP request to the
    # push service (FCM/Mozilla/etc.) and blocks until it responds.
    # Calling it directly inside this `async def` blocked the entire
    # FastAPI event loop for that round-trip — and this function runs
    # at the end of *every* orchestration run and *every* deployment,
    # so every build notification was stalling the whole server for
    # every other user, not just this one. asyncio.to_thread() moves
    # each send onto a worker thread so the event loop stays responsive.
    for sub in subscriptions:
        try:
            await asyncio.to_thread(_send_one, payload, sub)
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in (404, 410):
                await session.delete(sub)
                await session.commit()
            else:
                logger.warning("Push failed for subscription %s: %s", sub.id, exc)
