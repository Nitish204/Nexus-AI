"""
Tests for LLM cost tracking end-to-end through AgentBase.run(): a
streamed completion's usage chunk must turn into a persisted
TokenUsage row with the right cost, and a provider that never sends
usage data must not fabricate one.
"""
import json
from types import SimpleNamespace

import pytest
from sqlmodel import select

from app.agents.backend_engineer import BackendEngineerAgent
from app.db.models import AgentRole, Task, TaskStatus, TokenUsage


def _delta_chunk(text):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))], usage=None)


def _usage_chunk(prompt_tokens, completion_tokens):
    return SimpleNamespace(
        choices=[],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


class FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for c in self._chunks:
            yield c


def make_fake_client(chunks):
    async def create(**kwargs):
        return FakeStream(chunks)

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


@pytest.mark.asyncio
async def test_successful_call_persists_token_usage_with_cost(session, project):
    task = Task(
        project_id=project.id, title="Build API", description="d",
        assigned_role=AgentRole.BACKEND_ENGINEER, status=TaskStatus.PENDING,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    body = json.dumps({"files": [{"path": "app/main.py", "content": "x", "language": "python"}], "notes": "n"})
    chunks = [_delta_chunk(body), _usage_chunk(prompt_tokens=1000, completion_tokens=500)]

    agent = BackendEngineerAgent(session)
    agent.model_name = "openai/gpt-oss-120b"
    agent.client = make_fake_client(chunks)

    await agent.run(task)

    result = await session.exec(select(TokenUsage).where(TokenUsage.task_id == task.id))
    rows = result.all()
    assert len(rows) == 1
    assert rows[0].prompt_tokens == 1000
    assert rows[0].completion_tokens == 500
    assert rows[0].cost_usd > 0
    assert rows[0].role == AgentRole.BACKEND_ENGINEER


@pytest.mark.asyncio
async def test_missing_usage_data_does_not_create_a_fabricated_row(session, project):
    """A local/self-hosted provider that never sends a usage chunk must
    not result in a fake $0 TokenUsage row being recorded as if cost
    tracking succeeded."""
    task = Task(
        project_id=project.id, title="Build API", description="d",
        assigned_role=AgentRole.BACKEND_ENGINEER, status=TaskStatus.PENDING,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    body = json.dumps({"files": [{"path": "app/main.py", "content": "x", "language": "python"}], "notes": "n"})
    chunks = [_delta_chunk(body)]  # no usage chunk at all

    agent = BackendEngineerAgent(session)
    agent.client = make_fake_client(chunks)

    await agent.run(task)

    result = await session.exec(select(TokenUsage).where(TokenUsage.task_id == task.id))
    assert result.all() == []
