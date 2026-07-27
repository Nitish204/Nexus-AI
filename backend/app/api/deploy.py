from fastapi import APIRouter, BackgroundTasks, Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models import Deployment
from app.db.session import get_session
from app.services.deployment import run_deployment

router = APIRouter(prefix="/api/projects/{project_id}/deploy", tags=["deployment"])


@router.post("")
async def trigger_deployment(
    project_id: str, background_tasks: BackgroundTasks, session: AsyncSession = Depends(get_session)
):
    """One-click deploy — returns immediately, actual status streams
    over the WebSocket as 'deployment_status' events."""
    background_tasks.add_task(run_deployment, session, project_id)
    return {"status": "accepted", "project_id": project_id}


@router.get("")
async def list_deployments(project_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.exec(select(Deployment).where(Deployment.project_id == project_id))
    return result.all()
