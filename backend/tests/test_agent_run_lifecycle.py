"""
Tests for AgentBase.run() itself — the streaming/retry/status-transition
machinery shared by every agent — as opposed to test_agents.py and
test_agents_other_roles.py, which only test each agent's
handle_response(). This is the part of the system that decides
whether a task ends up IN_REVIEW or FAILED, and whether a rate limit
gets retried, so it's worth locking down independent of any one
agent's JSON schema.
"""
import json
from types import SimpleNamespace

import httpx
import pytest
from openai import APIStatusError
from sqlmodel import select

from app.agents.backend_engineer import BackendEngineerAgent
from app.db.models import AgentMessage, AgentRole, Task, TaskStatus


def _delta_chunk(text):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))], usage=None)


class FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for c in self._chunks:
            yield c


async def _make_task(session, project):
    task = Task(
        project_id=project.id, title="Build API", description="d",
        assigned_role=AgentRole.BACKEND_ENGINEER, status=TaskStatus.PENDING,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


def _fake_api_status_error(status_code):
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status_code, request=request, json={"error": {"message": "boom"}})
    return APIStatusError("boom", response=response, body={"error": {"message": "boom"}})


@pytest.mark.asyncio
async def test_run_marks_task_in_review_on_success(session, project):
    task = await _make_task(session, project)
    body = json.dumps({"files": [{"path": "app/main.py", "content": "x", "language": "python"}], "notes": "n"})

    async def create(**kwargs):
        return FakeStream([_delta_chunk(body)])

    agent = BackendEngineerAgent(session)
    agent.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    updated = await agent.run(task)

    assert updated.status == TaskStatus.IN_REVIEW
    assert updated.result_summary  # first 280 chars of the model's raw output


@pytest.mark.asyncio
async def test_run_marks_task_failed_on_empty_response(session, project):
    task = await _make_task(session, project)

    async def create(**kwargs):
        return FakeStream([])  # provider returns nothing at all

    agent = BackendEngineerAgent(session)
    agent.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    updated = await agent.run(task)

    assert updated.status == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_run_marks_task_failed_on_malformed_json(session, project):
    task = await _make_task(session, project)
    body = "this is not json"

    async def create(**kwargs):
        return FakeStream([_delta_chunk(body)])

    agent = BackendEngineerAgent(session)
    agent.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    updated = await agent.run(task)

    assert updated.status == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_run_retries_once_on_429_then_succeeds(session, project, monkeypatch):
    """A 429 on the first attempt should trigger exactly one retry
    (after a real-world 25s backoff, mocked out here) and then
    succeed if the second attempt works."""
    task = await _make_task(session, project)
    body = json.dumps({"files": [{"path": "app/main.py", "content": "x", "language": "python"}], "notes": "n"})

    calls = {"n": 0}

    async def create(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _fake_api_status_error(429)
        return FakeStream([_delta_chunk(body)])

    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr("app.agents.base.asyncio.sleep", fake_sleep)

    agent = BackendEngineerAgent(session)
    agent.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    updated = await agent.run(task)

    assert calls["n"] == 2
    assert sleep_calls == [25]
    assert updated.status == TaskStatus.IN_REVIEW


@pytest.mark.asyncio
async def test_run_fails_after_persistent_429(session, project, monkeypatch):
    task = await _make_task(session, project)

    async def create(**kwargs):
        raise _fake_api_status_error(429)

    async def fake_sleep(seconds):
        return None

    monkeypatch.setattr("app.agents.base.asyncio.sleep", fake_sleep)

    agent = BackendEngineerAgent(session)
    agent.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    updated = await agent.run(task)

    assert updated.status == TaskStatus.FAILED
    messages = (await session.exec(select(AgentMessage).where(AgentMessage.task_id == task.id))).all()
    assert any("rate limit" in m.content.lower() for m in messages)
