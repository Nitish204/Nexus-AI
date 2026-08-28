from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.session import get_session
from app.services.github_export import export_project_to_github, GitHubExportError
from app.api.projects import get_current_user_id, get_owned_project

router = APIRouter(prefix="/api/projects/{project_id}/github-export", tags=["github-export"])


class GitHubExportRequest(BaseModel):
    repo_name: str
    private: bool = True
    access_token: str | None = None  # optional: pass the user's own GitHub token from client-side OAuth


@router.post("")
async def export_to_github(
    project_id: str,
    body: GitHubExportRequest,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    await get_owned_project(project_id, session, user_id)
    try:
        result = await export_project_to_github(
            session, project_id, body.repo_name, body.private, body.access_token
        )
    except GitHubExportError as exc:
        raise HTTPException(400, str(exc))
    return result
