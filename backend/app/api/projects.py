import asyncio
from fastapi import APIRouter, Depends, BackgroundTasks
from pydantic import BaseModel
from sqlmodel import select, desc
from sqlmodel.ext.asyncio.session import AsyncSession
from app.db.models import GeneratedFile, Project, Task, Deployment
from app.db.session import get_session, get_session_context
from app.services.orchestrator import Orchestrator

router = APIRouter(prefix="/api/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    name: str
    description: str = ""
    owner_id: str = "demo-user"


class CommandRequest(BaseModel):
    """A text or voice-transcribed command, e.g.
    'Build a Django authentication system with JWT and PostgreSQL'."""
    text: str


@router.post("")
async def create_project(body: CreateProjectRequest, session: AsyncSession = Depends(get_session)):
    project = Project(name=body.name, description=body.description, owner_id=body.owner_id)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


@router.get("/{project_id}")
async def get_project(project_id: str, session: AsyncSession = Depends(get_session)):
    return await session.get(Project, project_id)


@router.get("/{project_id}/files")
async def list_files(project_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.exec(select(GeneratedFile).where(GeneratedFile.project_id == project_id))
    return result.all()


@router.get("/{project_id}/tasks")
async def list_tasks(project_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.exec(select(Task).where(Task.project_id == project_id))
    return result.all()


@router.get("/{project_id}/deployment")
async def get_latest_deployment(project_id: str, session: AsyncSession = Depends(get_session)):
    """Returns the most recent deployment attempt for this project, so
    the frontend can poll for the result even if it missed the live
    WebSocket event (e.g. reconnected right after deploy finished)."""
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
):
    """Fires the orchestrator in the background so the HTTP call returns
    immediately; all progress streams over the WebSocket instead."""
    background_tasks.add_task(_run_orchestrator_in_background, project_id, body.text)
    return {"status": "accepted", "project_id": project_id}
