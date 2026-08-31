"""
NEXUS — Web Push notifications for the installed PWA.
"""
from __future__ import annotations

import json
import logging

from pywebpush import webpush, WebPushException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.db.models import Project, PushSubscription

settings = get_settings()
logger = logging.getLogger("nexus.push")


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

    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.vapid_subject},
            )
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in (404, 410):
                await session.delete(sub)
                await session.commit()
            else:
                logger.warning("Push failed for subscription %s: %s", sub.id, exc)
