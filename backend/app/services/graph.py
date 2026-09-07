"""
NEXUS — Knowledge graph service (Phase 4).

Parses generated files to extract relationships — file imports file,
file defines API route, route reads/writes DB table — and stores them
as GraphEdge rows. The frontend renders this as a literal 3D graph so
the person can see how their generated system fits together, not just
a flat file list.

Kept as plain Postgres rows (not a separate Neo4j instance) to keep the
whole stack deployable as one Postgres DB in early phases. `networkx` is
used in-process for any traversal/analysis needed later (e.g. detecting
orphan files, circular imports) without adding infra.
"""
from __future__ import annotations

import ast
import re

import networkx as nx
from sqlmodel import select, delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models import GeneratedFile, GraphEdge

# Recognize common API decorators/route calls across FastAPI/Flask/Django
# without needing a full framework-aware parser — good enough for
# surfacing structure, not a source of truth for routing.
ROUTE_PATTERN = re.compile(
    r"""@?\w*\.(?:get|post|put|delete|patch)\s*\(\s*["']([^"']+)["']"""
)
TABLE_PATTERN = re.compile(r"""(?:__tablename__\s*=\s*["'](\w+)["']|class\s+(\w+)\(.*Base.*\):)""")
# Deliberately case-sensitive (no re.IGNORECASE): SQL keywords in
# generated code are conventionally uppercase ("SELECT * FROM users"),
# and matching case-insensitively made this collide with Python's own
# lowercase `from` keyword — "from app.db import models" was being
# misread as a SQL FROM clause and produced a bogus
# ("app", "reads_or_writes_table") edge on every single import.
SQL_TABLE_HINT = re.compile(r"""(?:FROM|INTO|UPDATE)\s+["'`]?(\w+)["'`]?""")


def _extract_python_edges(file: GeneratedFile) -> list[tuple[str, str, str]]:
    """Returns (source, target, relation) triples for one Python file."""
    edges: list[tuple[str, str, str]] = []
    try:
        tree = ast.parse(file.content)
    except SyntaxError:
        return edges

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                edges.append((file.path, alias.name, "imports"))
        elif isinstance(node, ast.ImportFrom) and node.module:
            # Previously recorded only the module ("app.db" for
            # "from app.db import models"), silently dropping which
            # name(s) were actually imported. Resolving to the full
            # dotted path per imported name ("app.db.models") makes the
            # graph distinguish "imports the models module" from
            # "imports the config module" when a file does
            # `from app.db import models, config` — both used to
            # collapse into one indistinguishable "app.db" edge.
            for alias in node.names:
                edges.append((file.path, f"{node.module}.{alias.name}", "imports"))

    for match in ROUTE_PATTERN.finditer(file.content):
        edges.append((file.path, match.group(1), "defines_api"))

    for match in TABLE_PATTERN.finditer(file.content):
        table_name = match.group(1) or match.group(2)
        if table_name:
            edges.append((file.path, table_name, "defines_table"))

    for match in SQL_TABLE_HINT.finditer(file.content):
        edges.append((file.path, match.group(1), "reads_or_writes_table"))

    return edges


IMPORT_JS_PATTERN = re.compile(r"""import\s+.*?from\s+["']([^"']+)["']""")
FETCH_PATTERN = re.compile(r"""fetch\(\s*[`"']([^`"']+)[`"']""")


def _extract_js_edges(file: GeneratedFile) -> list[tuple[str, str, str]]:
    edges: list[tuple[str, str, str]] = []
    for match in IMPORT_JS_PATTERN.finditer(file.content):
        edges.append((file.path, match.group(1), "imports"))
    for match in FETCH_PATTERN.finditer(file.content):
        edges.append((file.path, match.group(1), "calls_api"))
    return edges


def extract_edges(file: GeneratedFile) -> list[tuple[str, str, str]]:
    if file.language == "python":
        return _extract_python_edges(file)
    if file.language in ("javascript", "jsx", "typescript", "tsx"):
        return _extract_js_edges(file)
    return []


async def rebuild_graph_for_project(session: AsyncSession, project_id: str) -> nx.DiGraph:
    """Re-derives the full graph for a project from its current files.
    Called after every task settles so the graph never drifts from
    what's actually in GeneratedFile."""
    await session.exec(delete(GraphEdge).where(GraphEdge.project_id == project_id))

    result = await session.exec(select(GeneratedFile).where(GeneratedFile.project_id == project_id))
    files = result.all()

    graph = nx.DiGraph()
    for file in files:
        graph.add_node(file.path, kind="file", language=file.language, written_by=file.written_by)

    for file in files:
        for source, target, relation in extract_edges(file):
            graph.add_edge(source, target, relation=relation)
            session.add(GraphEdge(project_id=project_id, source=source, target=target, relation=relation))

    await session.commit()
    return graph


def graph_summary_stats(graph: nx.DiGraph) -> dict:
    """Cheap health signals for the analytics panel: orphan files (no
    edges at all) and any import cycles, which usually indicate a
    design problem worth flagging to the person."""
    orphans = [n for n in graph.nodes if graph.degree(n) == 0]
    try:
        cycles = list(nx.simple_cycles(graph))
    except Exception:
        cycles = []
    return {
        "node_count": graph.number_of_nodes(),
        "edge_count": graph.number_of_edges(),
        "orphan_files": orphans,
        "cycle_count": len(cycles),
    }
