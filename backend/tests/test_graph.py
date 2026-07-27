"""
Tests for app.services.graph — edge extraction from generated files.

Covers the AST-based Python parsing and the regex-based JS parsing
separately, plus the end-to-end rebuild against the DB.
"""
import pytest
from sqlmodel import select

from app.db.models import AgentRole, GeneratedFile, GraphEdge
from app.services.graph import extract_edges, rebuild_graph_for_project


def _file(path, content, language="python"):
    return GeneratedFile(
        project_id="proj-1", path=path, content=content,
        language=language, written_by=AgentRole.BACKEND_ENGINEER,
    )


def test_python_import_edges_are_extracted():
    f = _file("app/main.py", "import os\nfrom app.db import models\n")
    edges = extract_edges(f)

    relations = {(t, r) for _, t, r in edges}
    assert ("os", "imports") in relations
    # from X import Y edges resolve to the full dotted path X.Y, not
    # just the module — more useful for the knowledge graph, and avoids
    # colliding with Python's "from" keyword when scanning for SQL hints
    assert ("app.db.models", "imports") in relations


def test_sql_hint_extraction_does_not_false_positive_on_python_imports():
    """Regression test: 'from X import Y' must never be mistaken for a
    SQL FROM clause just because both use the word 'from'."""
    f = _file("app/main.py", "from app.db import models\n")
    edges = extract_edges(f)

    relations = [(t, r) for _, t, r in edges]
    assert not any(r == "reads_or_writes_table" for _, r in relations)


def test_sql_hint_is_extracted_from_actual_query_strings():
    f = _file("app/queries.py", 'query = "SELECT * FROM users WHERE id = 1"\n')
    edges = extract_edges(f)

    relations = [(t, r) for _, t, r in edges]
    assert ("users", "reads_or_writes_table") in relations


def test_python_api_route_edges_are_extracted():
    f = _file("app/views.py", '@app.get("/users/{id}")\ndef get_user(id): ...\n')
    edges = extract_edges(f)

    assert ("app/views.py", "/users/{id}", "defines_api") in edges


def test_python_table_definition_edges_are_extracted():
    f = _file("app/models.py", 'class User(Base):\n    __tablename__ = "users"\n')
    edges = extract_edges(f)

    relations = [(t, r) for _, t, r in edges]
    assert ("users", "defines_table") in relations


def test_malformed_python_file_returns_no_edges_without_crashing():
    f = _file("app/broken.py", "def foo(:\n  this is not valid python")
    edges = extract_edges(f)
    assert edges == []


def test_js_import_and_fetch_edges_are_extracted():
    f = _file(
        "src/App.jsx",
        'import React from "react";\nfetch("/api/users").then(r => r.json());\n',
        language="javascript",
    )
    edges = extract_edges(f)

    relations = {(t, r) for _, t, r in edges}
    assert ("react", "imports") in relations
    assert ("/api/users", "calls_api") in relations


def test_unsupported_language_returns_no_edges():
    f = _file("Dockerfile", "FROM python:3.12-slim", language="dockerfile")
    assert extract_edges(f) == []


@pytest.mark.asyncio
async def test_rebuild_graph_persists_edges_and_clears_stale_ones(session, project):
    f1 = GeneratedFile(
        project_id=project.id, path="app/main.py", content="import os\n",
        language="python", written_by=AgentRole.BACKEND_ENGINEER,
    )
    session.add(f1)
    await session.commit()

    await rebuild_graph_for_project(session, project.id)

    result = await session.exec(select(GraphEdge).where(GraphEdge.project_id == project.id))
    edges = result.all()
    assert len(edges) == 1
    assert edges[0].target == "os"

    # rebuilding again with no files should clear stale edges, not duplicate them
    await session.exec(GeneratedFile.__table__.delete())  # simulate file removal
    await rebuild_graph_for_project(session, project.id)

    result = await session.exec(select(GraphEdge).where(GraphEdge.project_id == project.id))
    assert result.all() == []
