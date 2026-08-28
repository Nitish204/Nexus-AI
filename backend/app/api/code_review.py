from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models import GeneratedFile
from app.db.session import get_session
from app.services.code_review import review_file
from app.api.projects import get_current_user_id, get_owned_project

router = APIRouter(prefix="/api/projects/{project_id}/files/{file_id}/review", tags=["code-review"])


@router.post("")
async def review_generated_file(
    project_id: str,
    file_id: str,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    await get_owned_project(project_id, session, user_id)
    file = await session.get(GeneratedFile, file_id)
    if not file or file.project_id != project_id:
        raise HTTPException(404, "File not found in this project.")
    return await review_file(file)
