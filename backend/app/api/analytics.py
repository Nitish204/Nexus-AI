from fastapi import APIRouter, Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.db.models import AnalysisResult, GeneratedFile, TokenUsage
from app.db.session import get_session
from app.services.analysis import analyze_file
from app.api.projects import get_current_user_id, get_owned_project

router = APIRouter(prefix="/api/projects/{project_id}/analytics", tags=["analytics"])


@router.post("/run")
async def run_analysis(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    await get_owned_project(project_id, session, user_id)
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
async def get_analysis(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    await get_owned_project(project_id, session, user_id)
    result = await session.exec(select(AnalysisResult).where(AnalysisResult.project_id == project_id))
    return result.all()


@router.get("/cost")
async def get_llm_cost(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """
    LLM spend for this project: a total plus a per-role breakdown, so
    the UI can show e.g. "backend_engineer burned 70% of the budget"
    rather than only an opaque grand total. `is_estimated` is True on
    the total whenever *any* contributing row used the pricing
    fallback (see app/core/llm_pricing.py) — the caller doesn't need to
    inspect individual rows to know whether to render "$" or "~$".
    """
    await get_owned_project(project_id, session, user_id)

    result = await session.exec(select(TokenUsage).where(TokenUsage.project_id == project_id))
    rows = result.all()

    by_role: dict[str, dict] = {}
    total_cost = 0.0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    any_estimated = False

    for row in rows:
        role_key = row.role.value
        bucket = by_role.setdefault(
            role_key, {"cost_usd": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "calls": 0}
        )
        bucket["cost_usd"] += row.cost_usd
        bucket["prompt_tokens"] += row.prompt_tokens
        bucket["completion_tokens"] += row.completion_tokens
        bucket["calls"] += 1

        total_cost += row.cost_usd
        total_prompt_tokens += row.prompt_tokens
        total_completion_tokens += row.completion_tokens
        any_estimated = any_estimated or row.is_estimated

    for bucket in by_role.values():
        bucket["cost_usd"] = round(bucket["cost_usd"], 6)

    return {
        "project_id": project_id,
        "total_cost_usd": round(total_cost, 6),
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "total_calls": len(rows),
        "is_estimated": any_estimated,
        "by_role": by_role,
    }
