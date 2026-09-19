import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, BackgroundTasks, Header, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import select, desc
from sqlmodel.ext.asyncio.session import AsyncSession
from app.core.security import decode_access_token, api_key_lookup_prefix, verify_api_key
from app.core.token_revocation import is_token_revoked
from app.db.models import AgentMessage, AnalysisResult, ApiKey, GeneratedFile, GraphEdge, Project, Task, Deployment
from app.db.session import get_session, get_session_context
from app.services.orchestrator import Orchestrator
from sqlalchemy.exc import IntegrityError

router = APIRouter(prefix="/api/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    name: str
    description: str = ""


class RenameProjectRequest(BaseModel):
    name: str


class CommandRequest(BaseModel):
    """A text or voice-transcribed command, e.g.
    'Build a Django authentication system with JWT and PostgreSQL'."""
    text: str


async def _validate_session_payload(payload: dict) -> str:
    """
    Shared by both auth entry points (this function and
    api/auth.py's _resolve_user_id) so there's exactly one place that
    decides a decoded token payload is actually a valid, current
    session — not two copies that could quietly drift apart.

    Explicitly rejects a 2FA-pending token (see
    core/security.create_2fa_pending_token): that token intentionally
    carries no `jti`, and is_token_revoked() treats a missing jti as
    "nothing to check, not revoked" — without this explicit purpose
    check, a pending-2FA token would be silently usable as a real,
    fully-authenticated session before the user ever entered their
    second factor, which would defeat the entire point of 2FA.
    """
    if payload.get("purpose") == "2fa_pending":
        raise HTTPException(401, "Invalid or expired token.")
    if await is_token_revoked(payload.get("jti")):
        raise HTTPException(401, "This session has been signed out. Please sign in again.")
    return payload["sub"]


async def _resolve_api_key(raw_key: str, session: AsyncSession) -> str:
    """
    Can't hash the incoming key and look up a row by that hash directly
    — bcrypt is deliberately non-deterministic (salted), so the same
    input produces a different hash every time, which rules out a
    simple "WHERE key_hash = hash(presented_key)" query. Instead: use
    the plaintext key_prefix (stored specifically for this) to narrow
    to the — in practice, exactly one, given negligible collision odds
    — candidate row(s), then verify the FULL presented key against
    that candidate's real bcrypt hash.
    """
    prefix = api_key_lookup_prefix(raw_key)
    result = await session.exec(select(ApiKey).where(ApiKey.key_prefix == prefix, ApiKey.revoked == False))
    for candidate in result.all():
        if verify_api_key(raw_key, candidate.key_hash):
            candidate.last_used_at = datetime.now(timezone.utc)
            session.add(candidate)
            await session.commit()
            return candidate.owner_id
    raise HTTPException(401, "Invalid API key.")


async def get_current_user_id(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    session: AsyncSession = Depends(get_session),
) -> str:
    """
    Three auth paths, all landing here:
      - Programmatic access: `X-API-Key: nxs_...`. Same reasoning as
        the Bearer path below re: CSRF — a custom header is never
        attached automatically by a browser to a request the user
        didn't initiate, so this needs no CSRF check either. Checked
        first since its format (the "nxs_" prefix) is unambiguous.
      - Mobile app: sends `Authorization: Bearer <token>`. A bearer
        header is never attached automatically by anything other than
        code that explicitly chose to — a malicious page can't force a
        victim's phone to send one — so this path needs no further
        CSRF check.
      - Web app: no header, relies on the httpOnly `nexus_session`
        cookie instead. Cookies ARE attached automatically by the
        browser to any matching request, including ones a malicious
        cross-site page tricks the browser into making — so any
        state-changing request authenticated this way must also prove
        it can read this site's own cookies (which a cross-site
        attacker cannot) by echoing the `nexus_csrf` cookie's value
        back in a header. This is the standard "double-submit cookie"
        CSRF defense.
    """
    if x_api_key and x_api_key.startswith("nxs_"):
        return await _resolve_api_key(x_api_key, session)

    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        payload = decode_access_token(token)
        if not payload:
            raise HTTPException(401, "Invalid or expired token.")
        return await _validate_session_payload(payload)

    token = request.cookies.get("nexus_session")
    if not token:
        raise HTTPException(401, "Missing authentication.")
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(401, "Invalid or expired token.")
    user_id = await _validate_session_payload(payload)

    if request.method not in ("GET", "HEAD", "OPTIONS"):
        csrf_cookie = request.cookies.get("nexus_csrf")
        csrf_header = request.headers.get("x-csrf-token")
        if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
            raise HTTPException(403, "CSRF check failed — please refresh the page and try again.")

    return user_id


async def get_owned_project(
    project_id: str,
    session: AsyncSession,
    user_id: str,
) -> Project:
    """Fetches a project and verifies it belongs to the requesting user.
    Returns 404 (not 403) if it exists but belongs to someone else, so
    we don't reveal that a project ID is valid at all."""
    project = await session.get(Project, project_id)
    if not project or project.owner_id != user_id:
        raise HTTPException(404, "Project not found.")
    return project


@router.post("")
async def create_project(
    body: CreateProjectRequest,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    project = Project(name=body.name, description=body.description, owner_id=user_id)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


@router.get("")
async def list_my_projects(
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    result = await session.exec(select(Project).where(Project.owner_id == user_id))
    return result.all()


@router.get("/{project_id}")
async def get_project(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    return await get_owned_project(project_id, session, user_id)


@router.patch("/{project_id}")
async def rename_project(
    project_id: str,
    body: RenameProjectRequest,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    project = await get_owned_project(project_id, session, user_id)
    project.name = body.name.strip() or project.name
    project.name_is_default = False
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    project = await get_owned_project(project_id, session, user_id)

    # AgentMessage has a foreign key to task.id (not project_id directly),
    # so it has to be cleared out BEFORE the Task rows it references are
    # deleted below — deleting a Task that still has AgentMessage rows
    # pointing at it violates the FK constraint in Postgres, which was
    # silently crashing this whole endpoint for any project that had ever
    # actually run (i.e. had agent activity logged).
    task_ids = (await session.exec(select(Task.id).where(Task.project_id == project_id))).all()
    if task_ids:
        messages = await session.exec(select(AgentMessage).where(AgentMessage.task_id.in_(task_ids)))
        for msg in messages.all():
            await session.delete(msg)

    # Clean up remaining dependent rows — no cascade configured at the DB
    # level, so orphaned rows would otherwise be left behind silently.
    for model in (GeneratedFile, Task, Deployment, GraphEdge, AnalysisResult):
        result = await session.exec(select(model).where(model.project_id == project_id))
        for row in result.all():
            await session.delete(row)
    await session.delete(project)
    try:
        await session.commit()
    except IntegrityError:
        # Belt-and-braces: if some other dependent row we don't know
        # about yet still references this project, fail cleanly with a
        # real HTTP error instead of letting the exception propagate
        # unhandled — which is what silently broke the connection
        # before (surfacing to the browser as a bare "Failed to fetch").
        await session.rollback()
        raise HTTPException(
            409,
            "Couldn't delete this project — some related data is still linked to it. "
            "Please try again or contact support if this persists.",
        )
    return {"status": "deleted", "project_id": project_id}


@router.get("/{project_id}/files")
async def list_files(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    await get_owned_project(project_id, session, user_id)
    result = await session.exec(select(GeneratedFile).where(GeneratedFile.project_id == project_id))
    return result.all()


@router.get("/{project_id}/tasks")
async def list_tasks(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    await get_owned_project(project_id, session, user_id)
    result = await session.exec(select(Task).where(Task.project_id == project_id))
    return result.all()


@router.get("/{project_id}/deployment")
async def get_latest_deployment(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    await get_owned_project(project_id, session, user_id)
    result = await session.exec(
        select(Deployment)
        .where(Deployment.project_id == project_id)
        .order_by(desc(Deployment.created_at))
        .limit(1)
    )
    return result.first()


async def _run_orchestrator_in_background(project_id: str, text: str):
    """Runs with its OWN fresh database session/connection, independent
    of the HTTP request's session (which is closed by the time this
    background task actually executes)."""
    async with get_session_context() as session:
        orchestrator = Orchestrator(session)
        await orchestrator.kick_off(project_id, text)


@router.post("/{project_id}/command")
async def submit_command(
    project_id: str,
    body: CommandRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """Fires the orchestrator in the background so the HTTP call returns
    immediately; all progress streams over the WebSocket instead."""
    await get_owned_project(project_id, session, user_id)
    background_tasks.add_task(_run_orchestrator_in_background, project_id, body.text)
    return {"status": "accepted", "project_id": project_id}
