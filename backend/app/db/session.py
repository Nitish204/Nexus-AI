from contextlib import asynccontextmanager

from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession  # SQLModel's session, not plain SQLAlchemy's

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
    # Bug fix: without these, SQLAlchemy will hand out a connection from
    # its pool without checking whether it's still alive first. Neon
    # (like most managed/serverless Postgres) silently drops idle
    # connections after a period of inactivity — completely normal on a
    # low-traffic deploy where requests might be minutes or hours apart.
    # The *next* request after any idle gap would then get handed a
    # already-dead connection and crash immediately with something like
    # "connection was closed in the middle of operation" — a bigger,
    # recurring version of the exact class of bug that just caused the
    # login outage (a connection not reflecting the database's current
    # state). pool_pre_ping issues a cheap "is this connection still
    # alive" check before handing it out, transparently reconnecting if
    # not. pool_recycle proactively retires connections older than 5
    # minutes so they never get old enough to be silently dropped by the
    # server in the first place.
    pool_pre_ping=True,
    pool_recycle=300,
)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_session():
    """Used as a FastAPI dependency — tied to the request's lifetime."""
    async with async_session_maker() as session:
        yield session


@asynccontextmanager
async def get_session_context():
    """Used for background tasks — an independent session with its own
    lifetime, not tied to any HTTP request. This is what lets the
    orchestrator keep running (and committing) after the request that
    triggered it has already returned its response."""
    async with async_session_maker() as session:
        yield session
