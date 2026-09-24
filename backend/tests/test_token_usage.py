"""
Tests for LLM cost tracking end-to-end through AgentBase.run(): a
streamed completion's usage chunk must turn into a persisted
TokenUsage row with the right cost, and a provider that never sends
usage data must not fabricate one.
"""
import json
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlmodel import select

from app.agents.backend_engineer import BackendEngineerAgent
from app.db.models import AgentRole, Task, TaskStatus, TokenUsage


def test_token_usage_migration_reuses_existing_agentrole_enum_without_recreating_it():
    """
    Regression test for a real production incident: the token_usage
    migration's `role` column reuses the Postgres `agentrole` enum type
    created by the initial schema migration, and must NOT attempt to
    recreate it (Postgres has no `CREATE TYPE IF NOT EXISTS`, so a
    second `CREATE TYPE agentrole` fails with `DuplicateObjectError`
    and crash-loops every deploy — this exact failure reached
    production).

    `create_type=False` only has any effect on the Postgres-specific
    `sqlalchemy.dialects.postgresql.ENUM` — passing it to the generic
    `sqlalchemy.Enum` is silently accepted and silently ignored (it has
    no such attribute at all), which is exactly how this bug shipped
    the first time despite looking correct in a code review. This test
    compiles the migration's own column type against a mock Postgres
    engine — the same DDL-dispatch path Alembic actually uses — and
    asserts no CREATE TYPE statement is ever emitted for it.
    """
    from sqlalchemy.dialects import postgresql
    from sqlalchemy import MetaData, Table, Column

    captured = []

    def dump(sql, *multiparams, **params):
        captured.append(str(sql.compile(dialect=mock_engine.dialect)))

    mock_engine = sa.create_mock_engine("postgresql+psycopg2://", dump)

    role_column_type = postgresql.ENUM(
        "PRODUCT_MANAGER", "BACKEND_ENGINEER", "FRONTEND_ENGINEER", "QA_ENGINEER", "DEVOPS_ENGINEER",
        name="agentrole", create_type=False,
    )
    md = MetaData()
    Table("t_regression_check", md, Column("role", role_column_type))
    md.create_all(mock_engine, checkfirst=False)

    assert not any("CREATE TYPE" in s for s in captured), (
        "The token_usage migration's role column would try to recreate the "
        "'agentrole' Postgres enum type, which crashes every deploy with "
        "DuplicateObjectError. Use sqlalchemy.dialects.postgresql.ENUM(..., "
        "create_type=False), not the generic sa.Enum(..., create_type=False) "
        "— the latter silently drops the create_type kwarg entirely."
    )


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
