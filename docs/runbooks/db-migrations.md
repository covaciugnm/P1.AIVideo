# Database migrations (Phase 6B)

Alembic powers schema migrations. Until Phase 6B, the runtime relied on
``Base.metadata.create_all()`` from ``app.core.db.init_db()`` — that
path stayed for tests (SQLite in-memory, fresh every run) but real
deployments now use ``alembic upgrade head`` instead.

## At a glance

| Action | Command |
|---|---|
| Apply migrations | `make db-upgrade` |
| Revert one | `make db-downgrade` |
| Revert N | `make db-downgrade STEP=-N` |
| Current revision | `make db-current` |
| History | `make db-history` |
| New migration after a model change | `make db-migrate MSG="add foo to jobs"` |

Every `db-*` target shells to `alembic` inside `backend/`. The
`DATABASE_URL` is resolved by `backend/alembic/env.py` from
`app.core.config.Settings.get_database_url()`, which honours the
`DATABASE_URL` env var first.

## Configuration

`alembic.ini` lives at `backend/alembic.ini`. It intentionally leaves
`sqlalchemy.url` blank — `env.py` rewrites it at runtime, picking from:

1. `-x url=…` on the CLI (lets a CI job target an ephemeral DB).
2. `DATABASE_URL` env var.
3. Composed from the `POSTGRES_*` fields in `.env`.

## Local dev (venv)

```bash
# 1. Pick a database (SQLite for quick iteration).
export DATABASE_URL='sqlite+aiosqlite:///./dev.sqlite'

# 2. Apply migrations.
make db-upgrade

# 3. After changing a model under backend/app/models/:
make db-migrate MSG="add narration_voice to jobs"
# Inspect the new file under backend/alembic/versions/, then:
make db-upgrade
```

## Docker light

The dev compose file no longer needs `make docker-light-reset` after a
schema-changing PR — run migrations against the live Postgres container
instead:

```bash
BACKEND_PORT=8001 FRONTEND_PORT=3010 POSTGRES_PORT=5433 REDIS_PORT=6380 \
  docker compose -f docker/compose.dev.yml up -d postgres redis backend

# Run migrations inside the backend container so it sees the in-network
# Postgres hostname.
docker exec aivideo-backend-1 alembic -c backend/alembic.ini upgrade head
```

Or from the host, pointing at the published Postgres port:

```bash
DATABASE_URL='postgresql+asyncpg://aivideo:changeme@localhost:5433/aivideo' \
  make db-upgrade
```

`make docker-light-reset` is still available for the truly fresh-start
case (it drops the postgres / redis / inputs / artifacts volumes). For
normal "add a column" PRs, `make db-upgrade` is the right tool.

## What's NOT auto-run

- The FastAPI app does **NOT** call `alembic upgrade head` on startup.
  Migrations are an operator action; running them on app boot can hide a
  failure across replicas.
- `init_db()` in `app.core.db` still runs `Base.metadata.create_all()`.
  That's fine for tests (every test fixture resets the engine and
  starts from an empty SQLite in-memory DB). Production code never
  reaches that path in normal operation.
- No destructive migration is auto-applied. `make db-downgrade` requires
  an explicit invocation; `--sql` lets you preview SQL offline.

## Drift guard

`tests/integration/test_phase6b_migrations.py::test_autogenerate_against_head_yields_no_drift`
runs in the regular suite. If a future PR adds a column to a model
without a matching migration, that test fails fast with a clear hint to
run `make db-migrate MSG="…"`. It runs against a fresh SQLite file in
`tmp_path` so it's offline + deterministic.

## When to use which path

| Situation | Path |
|---|---|
| Tests | `init_db()` / `create_all` — fast, isolated, no Alembic |
| Local dev DB (Postgres) | `make db-upgrade` |
| Local dev DB (SQLite throwaway) | `make db-upgrade` with `DATABASE_URL=sqlite+aiosqlite:///./dev.sqlite` |
| Docker light | `docker exec aivideo-backend-1 alembic upgrade head` |
| Fresh wipe of dev volumes | `make docker-light-reset` (pre-Alembic recovery; still useful) |
| Production deploy | `alembic upgrade head` as a one-shot job; never on app startup |

## Generating a deploy SQL file (offline)

```bash
cd backend
alembic upgrade head --sql > /tmp/migration.sql
```

Useful for code review or shipping to a DBA for managed Postgres
deploys.
