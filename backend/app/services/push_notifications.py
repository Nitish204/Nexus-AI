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


async def send_push_to_user(session: AsyncSession, user_id: str, title: str, body: str, url: str = "/") -> None:
    """
    The general-purpose sender — anything that needs to notify a
    specific user, regardless of whether a project is involved at all
    (e.g. a security alert like account lockout has no project
    context). send_push_to_project_owner (below) is now a thin wrapper
    around this, so there's one actual sending implementation instead
    of two that could quietly drift apart.
    """
    if not settings.vapid_private_key or not settings.vapid_public_key:
        return

    result = await session.exec(select(PushSubscription).where(PushSubscription.user_id == user_id))
    subscriptions = result.all()
    if not subscriptions:
        return

    payload = json.dumps({"title": title, "body": body, "url": url})

    # Bug fix (kept from the original version): `webpush()` makes a real
    # synchronous HTTP request to the push service (FCM/Mozilla/etc.)
    # and blocks until it responds. Calling it directly inside this
    # `async def` would block the entire FastAPI event loop for that
    # round-trip for every other request being served at the same
    # time — asyncio.to_thread() moves each send onto a worker thread
    # so the event loop stays responsive.
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


async def send_push_to_project_owner(
    session: AsyncSession, project_id: str, title: str, body: str, url: str = "/"
) -> None:
    project = await session.get(Project, project_id)
    if not project:
        return
    await send_push_to_user(session, project.owner_id, title, body, url)
