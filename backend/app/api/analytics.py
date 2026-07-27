from fastapi import APIRouter, Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models import AnalysisResult, GeneratedFile
from app.db.session import get_session
from app.services.analysis import analyze_file

router = APIRouter(prefix="/api/projects/{project_id}/analytics", tags=["analytics"])


@router.post("/run")
async def run_analysis(project_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.exec(select(GeneratedFile).where(GeneratedFile.project_id == project_id))
    files = result.all()

    reports = []
    for f in files:
        report = await analyze_file(f)
        session.add(report)
        reports.append(report)
    await session.commit()
    return reports


@router.get("")
async def get_analysis(project_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.exec(select(AnalysisResult).where(AnalysisResult.project_id == project_id))
    return result.all()
