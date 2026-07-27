from fastapi import APIRouter, Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models import GraphEdge
from app.db.session import get_session
from app.services.graph import graph_summary_stats, rebuild_graph_for_project

router = APIRouter(prefix="/api/projects/{project_id}/graph", tags=["graph"])


@router.get("")
async def get_graph(project_id: str, session: AsyncSession = Depends(get_session)):
    """Returns raw edges — the frontend turns this into 3D nodes/links
    (e.g. via react-force-graph or a custom R3F layout)."""
    result = await session.exec(select(GraphEdge).where(GraphEdge.project_id == project_id))
    edges = result.all()
    nodes = sorted({e.source for e in edges} | {e.target for e in edges})
    return {
        "nodes": [{"id": n} for n in nodes],
        "links": [{"source": e.source, "target": e.target, "relation": e.relation} for e in edges],
    }


@router.post("/rebuild")
async def rebuild_graph(project_id: str, session: AsyncSession = Depends(get_session)):
    """Manual trigger — normally the orchestrator calls this automatically
    after every task, but exposed here for re-syncing after external edits."""
    graph = await rebuild_graph_for_project(session, project_id)
    return graph_summary_stats(graph)
