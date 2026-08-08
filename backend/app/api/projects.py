import asyncio
from fastapi import APIRouter, Depends, BackgroundTasks, Header, HTTPException
from pydantic import BaseModel
from sqlmodel import select, desc
from sqlmodel.ext.asyncio.session import AsyncSession
from app.core.security import decode_access_token
from app.db.models import AgentMessage, AnalysisResult, GeneratedFile, GraphEdge, Project, Task, Deployment
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


async def get_current_user_id(authorization: str = Header(...)) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token.")
    token = authorization.removeprefix("Bearer ").strip()
    user_id = decode_access_token(token)
    if not user_id:
        raise HTTPException(401, "Invalid or expired token.")
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
