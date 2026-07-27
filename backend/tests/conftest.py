"""
Shared test fixtures.

Uses an in-memory SQLite DB instead of the real Postgres — fast, no
external services required to run the suite. This means any test
relying on Postgres-only features (JSON column semantics, etc.) needs
its own care, but the SQLModel layer is DB-agnostic enough that this
covers the vast majority of logic worth testing here: agent output
parsing, orchestrator dependency resolution, and graph extraction.
"""
import os

# Must be set before any app module is imported — AgentBase constructs
# its OpenAI-compatible client eagerly in __init__, and the settings
# object is cached via lru_cache on first access.
os.environ.setdefault("GROQ_API_KEY", "test-dummy-key-not-used-for-real-calls")

import pytest
import pytest_asyncio
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.db.models import Project


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as s:
        yield s

    await engine.dispose()


@pytest_asyncio.fixture
async def project(session):
    p = Project(name="test-project", owner_id="test-user")
    session.add(p)
    await session.commit()
    await session.refresh(p)
    return p
