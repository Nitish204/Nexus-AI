from fastapi import APIRouter, BackgroundTasks, Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.db.models import Deployment
from app.db.session import get_session, get_session_context
from app.services.deployment import run_deployment
from app.api.projects import get_current_user_id, get_owned_project

router = APIRouter(prefix="/api/projects/{project_id}/deploy", tags=["deployment"])


async def _run_deployment_in_background(project_id: str):
    """Own fresh session, independent of the HTTP request's session
    (same fix as the orchestrator background task)."""
    async with get_session_context() as session:
        await run_deployment(session, project_id)


@router.post("")
async def trigger_deployment(
    project_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """One-click deploy — returns immediately, actual status streams
    over the WebSocket as 'deployment_status' events."""
    await get_owned_project(project_id, session, user_id)
    background_tasks.add_task(_run_deployment_in_background, project_id)
    return {"status": "accepted", "project_id": project_id}


@router.get("")
async def list_deployments(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    await get_owned_project(project_id, session, user_id)
    result = await session.exec(select(Deployment).where(Deployment.project_id == project_id))
    return result.all()
