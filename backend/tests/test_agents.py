"""
Tests for agent `handle_response` methods — the JSON-parsing boundary
between "whatever the LLM said" and the database. This is the most
failure-prone seam in the whole system (models occasionally wrap JSON
in prose or fences despite instructions), so it's worth locking down
with fixtures showing exactly what a well-formed response looks like.
"""
import json

import pytest
from sqlmodel import select

from app.agents.backend_engineer import BackendEngineerAgent
from app.agents.product_manager import ProductManagerAgent
from app.db.models import AgentRole, GeneratedFile, Task, TaskStatus


@pytest.mark.asyncio
async def test_product_manager_creates_tasks_with_correct_roles(session, project):
    parent_task = Task(
        project_id=project.id,
        title="Decompose feature request",
        description="Build a login system",
        assigned_role=AgentRole.PRODUCT_MANAGER,
        status=TaskStatus.PENDING,
    )
    session.add(parent_task)
    await session.commit()
    await session.refresh(parent_task)

    raw_response = json.dumps({
        "tasks": [
            {
                "title": "Build auth API",
                "description": "JWT-based login/register endpoints",
                "assigned_role": "backend_engineer",
                "depends_on_titles": [],
            },
            {
                "title": "Write auth tests",
                "description": "Test the login/register flow",
                "assigned_role": "qa_engineer",
                "depends_on_titles": ["Build auth API"],
            },
        ]
    })

    agent = ProductManagerAgent(session)
    await agent.handle_response(parent_task, raw_response)

    result = await session.exec(select(Task).where(Task.project_id == project.id))
    all_tasks = result.all()
    created = [t for t in all_tasks if t.id != parent_task.id]

    assert len(created) == 2
    by_title = {t.title: t for t in created}
    assert by_title["Build auth API"].assigned_role == AgentRole.BACKEND_ENGINEER
    assert by_title["Write auth tests"].assigned_role == AgentRole.QA_ENGINEER
    # dependency should be wired to the actual generated ID, not the title string
    assert by_title["Write auth tests"].depends_on == [by_title["Build auth API"].id]


@pytest.mark.asyncio
async def test_product_manager_handles_markdown_fenced_json(session, project):
    """Models sometimes wrap JSON in ```json fences despite instructions
    not to — handle_response must strip that before parsing."""
    parent_task = Task(
        project_id=project.id, title="t", description="d",
        assigned_role=AgentRole.PRODUCT_MANAGER, status=TaskStatus.PENDING,
    )
    session.add(parent_task)
    await session.commit()
    await session.refresh(parent_task)

    fenced = "```json\n" + json.dumps({
        "tasks": [{
            "title": "Do a thing", "description": "details",
            "assigned_role": "backend_engineer", "depends_on_titles": [],
        }]
    }) + "\n```"

    agent = ProductManagerAgent(session)
    await agent.handle_response(parent_task, fenced)

    result = await session.exec(select(Task).where(Task.project_id == project.id))
    created = [t for t in result.all() if t.id != parent_task.id]
    assert len(created) == 1
    assert created[0].title == "Do a thing"


@pytest.mark.asyncio
async def test_backend_engineer_persists_generated_files(session, project):
    task = Task(
        project_id=project.id, title="Build API", description="d",
        assigned_role=AgentRole.BACKEND_ENGINEER, status=TaskStatus.PENDING,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    raw_response = json.dumps({
        "files": [
            {"path": "app/main.py", "content": "print('hello')", "language": "python"},
            {"path": "app/models.py", "content": "class User: pass", "language": "python"},
        ],
        "notes": "Built a minimal API skeleton.",
    })

    agent = BackendEngineerAgent(session)
    await agent.handle_response(task, raw_response)

    result = await session.exec(select(GeneratedFile).where(GeneratedFile.project_id == project.id))
    files = result.all()
    assert {f.path for f in files} == {"app/main.py", "app/models.py"}
    assert all(f.written_by == AgentRole.BACKEND_ENGINEER for f in files)


@pytest.mark.asyncio
async def test_backend_engineer_raises_on_malformed_json(session, project):
    """handle_response should surface a parsing failure rather than
    silently writing garbage — the caller (AgentBase.run) is responsible
    for catching this and marking the task FAILED."""
    task = Task(
        project_id=project.id, title="Build API", description="d",
        assigned_role=AgentRole.BACKEND_ENGINEER, status=TaskStatus.PENDING,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    agent = BackendEngineerAgent(session)
    with pytest.raises(json.JSONDecodeError):
        await agent.handle_response(task, "this is not json at all")
