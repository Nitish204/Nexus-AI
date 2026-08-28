"""NEXUS — Plugin marketplace: browse the catalog, enable/disable
plugins per project."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models import Plugin, ProjectPlugin
from app.db.session import get_session
from app.api.projects import get_current_user_id, get_owned_project

router = APIRouter(prefix="/api/plugins", tags=["plugins"])

# Seed catalog — in a real marketplace this would be a curated table
# populated by publishers; a handful of realistic built-ins here so the
# marketplace UI has something real to browse immediately.
SEED_PLUGINS = [
    {"slug": "stripe-integration", "name": "Stripe Billing", "category": "integration",
     "description": "Adds a Backend Engineer task template for Stripe checkout + webhooks.",
     "author": "NEXUS Core", "config": {"env_vars": ["STRIPE_SECRET_KEY"]}},
    {"slug": "sendgrid-email", "name": "SendGrid Email", "category": "integration",
     "description": "Transactional email sending wired into generated backend code.",
     "author": "NEXUS Core", "config": {"env_vars": ["SENDGRID_API_KEY"]}},
    {"slug": "security-auditor", "name": "Security Auditor Agent", "category": "agent",
     "description": "An extra review pass focused solely on auth, secrets, and injection risks.",
     "author": "NEXUS Core", "config": {}},
    {"slug": "dark-glass-theme", "name": "Dark Glass Theme", "category": "theme",
     "description": "Frosted-glass dark UI theme for the workspace.",
     "author": "NEXUS Core", "config": {"theme_id": "dark-glass"}},
    {"slug": "saas-starter-template", "name": "SaaS Starter Template", "category": "template",
     "description": "Pre-fills the PM agent's plan with a standard SaaS skeleton (auth, billing, dashboard).",
     "author": "NEXUS Core", "config": {}},
]


class EnablePluginRequest(BaseModel):
    plugin_slug: str


async def _ensure_seeded(session: AsyncSession):
    existing = (await session.exec(select(Plugin))).all()
    if existing:
        return
    for p in SEED_PLUGINS:
        session.add(Plugin(**p))
    await session.commit()


@router.get("")
async def list_plugins(session: AsyncSession = Depends(get_session)):
    await _ensure_seeded(session)
    return (await session.exec(select(Plugin))).all()


@router.get("/projects/{project_id}")
async def list_enabled_plugins(
    project_id: str, session: AsyncSession = Depends(get_session), user_id: str = Depends(get_current_user_id)
):
    await get_owned_project(project_id, session, user_id)
    links = (await session.exec(select(ProjectPlugin).where(ProjectPlugin.project_id == project_id))).all()
    plugin_ids = [l.plugin_id for l in links]
    if not plugin_ids:
        return []
    result = await session.exec(select(Plugin).where(Plugin.id.in_(plugin_ids)))
    return result.all()


@router.post("/projects/{project_id}/enable")
async def enable_plugin(
    project_id: str, body: EnablePluginRequest,
    session: AsyncSession = Depends(get_session), user_id: str = Depends(get_current_user_id),
):
    await get_owned_project(project_id, session, user_id)
    await _ensure_seeded(session)
    plugin = (await session.exec(select(Plugin).where(Plugin.slug == body.plugin_slug))).first()
    if not plugin:
        raise HTTPException(404, "Plugin not found.")
    already = (await session.exec(
        select(ProjectPlugin).where(
            ProjectPlugin.project_id == project_id, ProjectPlugin.plugin_id == plugin.id
        )
    )).first()
    if already:
        return {"status": "already_enabled"}
    session.add(ProjectPlugin(project_id=project_id, plugin_id=plugin.id))
    await session.commit()
    return {"status": "enabled", "plugin": plugin.slug}


@router.post("/projects/{project_id}/disable")
async def disable_plugin(
    project_id: str, body: EnablePluginRequest,
    session: AsyncSession = Depends(get_session), user_id: str = Depends(get_current_user_id),
):
    await get_owned_project(project_id, session, user_id)
    plugin = (await session.exec(select(Plugin).where(Plugin.slug == body.plugin_slug))).first()
    if not plugin:
        raise HTTPException(404, "Plugin not found.")
    link = (await session.exec(
        select(ProjectPlugin).where(
            ProjectPlugin.project_id == project_id, ProjectPlugin.plugin_id == plugin.id
        )
    )).first()
    if link:
        await session.delete(link)
        await session.commit()
    return {"status": "disabled"}
