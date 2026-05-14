"""Alembic environment.

Phase 6B introduces real migrations to replace the dev-only
``Base.metadata.create_all()`` path. The setup deliberately:

- reuses :class:`app.core.config.Settings` so the DATABASE_URL the API
  reads is the same one Alembic operates against;
- uses SQLAlchemy's native async engine via ``run_sync()`` so we don't
  need a separate sync driver (no psycopg2 / psycopg3 — keeps the
  dependency footprint identical to Phase 6A);
- imports the existing ``Base.metadata`` so ``--autogenerate`` sees
  every model registered through ``app.models.__init__``.

The runtime FastAPI app does **not** run migrations on startup. Operators
invoke ``make db-upgrade`` (or ``alembic upgrade head`` from inside the
backend container) on deploy and after every schema-changing PR.
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import side effects: registers every model on ``Base.metadata`` so
# autogenerate sees them. The Phase 4F-2 ``jobs.provider_selection``
# column lives in ``app.models.job`` which is re-exported through
# ``app.models.__init__``.
from app.core.config import settings
from app.models import Base

# Alembic Config object — provides access to the values within the .ini.
config = context.config

# Set up Python logging according to the .ini file.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate to compare against.
target_metadata = Base.metadata


def _resolve_url() -> str:
    """Pick the database URL Alembic should run against.

    Resolution order:
      1. ``-x url=…`` on the ``alembic`` CLI (lets a CI job target an
         ephemeral DB without exporting env vars).
      2. ``sqlalchemy.url`` in alembic.ini (we leave this blank).
      3. The application settings' ``get_database_url()``, which itself
         honours the ``DATABASE_URL`` env var.
    """
    x_args = context.get_x_argument(as_dictionary=True)
    if "url" in x_args and x_args["url"]:
        return x_args["url"]
    ini_url = config.get_main_option("sqlalchemy.url")
    if ini_url:
        return ini_url
    return settings.get_database_url()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL to stdout.

    Useful for code review of generated migrations or for shipping a
    deploy SQL file to a DBA. No DB connection is opened.
    """
    url = _resolve_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        # SQLite: detect ALTER TABLE limitations and emit batch-mode
        # operations when needed. Postgres ignores this flag.
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    url = _resolve_url()
    # Push the resolved URL into the Alembic section so engine_from_config
    # sees it.
    section = dict(config.get_section(config.config_ini_section, {}) or {})
    section["sqlalchemy.url"] = url
    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
