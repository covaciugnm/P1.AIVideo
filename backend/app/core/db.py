"""Async SQLAlchemy engine + session factory.

Engine is lazily created on first use so DATABASE_URL overrides made by tests
take effect even if `app.core.db` has already been imported. Tests call
`reset_engine()` to drop any cached engine before changing the URL.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models import Base

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        url = settings.get_database_url()
        kwargs: dict = {"echo": False, "future": True}
        if url.startswith("sqlite"):
            # SQLite :memory: requires a single shared connection so every
            # session sees the same database. Tests rely on this.
            from sqlalchemy.pool import StaticPool

            kwargs["poolclass"] = StaticPool
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_async_engine(url, **kwargs)
        _sessionmaker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


def reset_engine() -> None:
    """Drop the cached engine. For tests; not for production use."""
    global _engine, _sessionmaker
    _engine = None
    _sessionmaker = None


async def init_db() -> None:
    """Create all tables. Phase 1 uses metadata.create_all; Alembic lands later."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
