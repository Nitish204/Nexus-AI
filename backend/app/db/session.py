from contextlib import asynccontextmanager

from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession  # SQLModel's session, not plain SQLAlchemy's

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=settings.debug, future=True)
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
