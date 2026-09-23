"""
handle_response tests for the three agents test_agents.py didn't cover
(QA, DevOps, Frontend) — same JSON-parsing boundary as the Backend/PM
agents, and the same regression class (path traversal, file
create-vs-update) applies to each of them independently since they all
go through AgentBase._write_generated_file separately.
"""
import json

import pytest
from sqlmodel import select

from app.agents.devops_engineer import DevOpsEngineerAgent
from app.agents.frontend_engineer import FrontendEngineerAgent
from app.agents.qa_engineer import QAEngineerAgent
from app.db.models import AgentRole, GeneratedFile, Task, TaskStatus


async def _make_task(session, project, role):
    task = Task(
        project_id=project.id, title="t", description="d",
        assigned_role=role, status=TaskStatus.PENDING,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


@pytest.mark.asyncio
async def test_qa_engineer_persists_test_files_and_logs_review_notes(session, project):
    task = await _make_task(session, project, AgentRole.QA_ENGINEER)

    raw_response = json.dumps({
        "files": [{"path": "tests/test_main.py", "content": "def test_x(): assert True", "language": "python"}],
        "review_notes": ["app/main.py has no input validation on the login endpoint"],
    })

    agent = QAEngineerAgent(session)
    await agent.handle_response(task, raw_response)

    result = await session.exec(select(GeneratedFile).where(GeneratedFile.project_id == project.id))
    files = result.all()
    assert {f.path for f in files} == {"tests/test_main.py"}
    assert files[0].written_by == AgentRole.QA_ENGINEER


@pytest.mark.asyncio
async def test_qa_engineer_handles_empty_review_notes(session, project):
    task = await _make_task(session, project, AgentRole.QA_ENGINEER)
    raw_response = json.dumps({"files": [], "review_notes": []})

    agent = QAEngineerAgent(session)
    # Should not raise even with no files and no issues.
    await agent.handle_response(task, raw_response)


@pytest.mark.asyncio
async def test_devops_engineer_persists_infra_files(session, project):
    task = await _make_task(session, project, AgentRole.DEVOPS_ENGINEER)

    raw_response = json.dumps({
        "files": [{"path": "Dockerfile", "content": "FROM python:3.12-slim", "language": "dockerfile"}],
        "notes": "Single-stage build for a small API.",
    })

    agent = DevOpsEngineerAgent(session)
    await agent.handle_response(task, raw_response)

    result = await session.exec(select(GeneratedFile).where(GeneratedFile.project_id == project.id))
    files = result.all()
    assert files[0].path == "Dockerfile"
    assert files[0].written_by == AgentRole.DEVOPS_ENGINEER


@pytest.mark.asyncio
async def test_devops_engineer_rejects_unsafe_path(session, project):
    task = await _make_task(session, project, AgentRole.DEVOPS_ENGINEER)

    raw_response = json.dumps({
        "files": [{"path": "/etc/passwd", "content": "evil", "language": "dockerfile"}],
        "notes": "n/a",
    })

    agent = DevOpsEngineerAgent(session)
    await agent.handle_response(task, raw_response)

    result = await session.exec(select(GeneratedFile).where(GeneratedFile.project_id == project.id))
    assert result.all() == []


@pytest.mark.asyncio
async def test_frontend_engineer_persists_component_files(session, project):
    task = await _make_task(session, project, AgentRole.FRONTEND_ENGINEER)

    raw_response = json.dumps({
        "files": [{"path": "src/components/LoginForm.jsx", "content": "export default function LoginForm() { return null; }", "language": "javascript"}],
        "notes": "Basic login form wired to /api/auth/login.",
    })

    agent = FrontendEngineerAgent(session)
    await agent.handle_response(task, raw_response)

    result = await session.exec(select(GeneratedFile).where(GeneratedFile.project_id == project.id))
    files = result.all()
    assert files[0].path == "src/components/LoginForm.jsx"
    assert files[0].written_by == AgentRole.FRONTEND_ENGINEER


@pytest.mark.asyncio
async def test_frontend_engineer_raises_on_malformed_json(session, project):
    task = await _make_task(session, project, AgentRole.FRONTEND_ENGINEER)
    agent = FrontendEngineerAgent(session)
    with pytest.raises(json.JSONDecodeError):
        await agent.handle_response(task, "not json")
