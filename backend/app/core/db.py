"""Async SQLAlchemy engine + session factory.

Engine is lazily created on first use so DATABASE_URL overrides made by tests
take effect even if `app.core.db` has already been imported.

Tests dispose the cached engine via one of two helpers:

- ``async_reset_engine()`` — **the right one for async tests.** Awaits
  ``engine.dispose()`` so any background driver threads (e.g. aiosqlite's
  worker) are joined before the event loop closes. Failing to do this
  produces ``PytestUnhandledThreadExceptionWarning: RuntimeError: Event
  loop is closed`` warnings.
- ``reset_engine()`` — synchronous fallback for non-async contexts. Does
  NOT call ``dispose()`` (it can't, since dispose is async). Prefer the
  async variant whenever an event loop is available.
"""
from __future__ import annotations

from sqlalchemy import event
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
        if url.startswith("sqlite"):
            # SQLite defaults to FK enforcement OFF. Phase 4E's DELETE
            # /jobs/{id} relies on the ON DELETE CASCADE constraints on
            # stage_runs / compliance_events / artifacts — without this
            # PRAGMA the cascade is a no-op and child rows are orphaned.
            sync_engine = _engine.sync_engine

            @event.listens_for(sync_engine, "connect")
            def _enable_sqlite_fk(dbapi_connection, _connection_record):  # noqa: ANN001
                cursor = dbapi_connection.cursor()
                try:
                    cursor.execute("PRAGMA foreign_keys=ON")
                finally:
                    cursor.close()

        _sessionmaker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


def reset_engine() -> None:
    """Drop the cached engine without awaiting dispose.

    Synchronous fallback. Async tests MUST call ``async_reset_engine``
    instead — otherwise driver worker threads (notably aiosqlite's) can
    outlive the test's event loop and emit ``RuntimeError: Event loop is
    closed`` from their teardown path.
    """
    global _engine, _sessionmaker
    _engine = None
    _sessionmaker = None


async def async_reset_engine() -> None:
    """Dispose the cached engine, then drop the references.

    ``AsyncEngine.dispose()`` closes every connection in the pool and
    joins driver background threads. Calling this from async test
    teardown ensures aiosqlite's worker thread is shut down before the
    event loop closes.
    """
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def init_db() -> None:
    """Create all tables. Phase 1 uses metadata.create_all; Alembic lands later."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
