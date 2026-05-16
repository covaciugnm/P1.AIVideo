"""Phase 6B — Alembic migration smoke + drift guard.

Validates:

- Alembic loads its env.py and sees ``Base.metadata`` (i.e. every model
  in ``app.models.__init__`` is registered).
- ``alembic upgrade head`` against a fresh SQLite file succeeds.
- ``alembic current`` reports the head revision after upgrade.
- ``alembic downgrade base`` cleanly drops every table.
- **Drift guard**: after ``upgrade head`` against the current
  ``Base.metadata``, ``alembic revision --autogenerate`` produces a
  migration whose ``upgrade()`` body is just ``pass``. If a model adds
  a column without a migration this test fails fast.

The tests shell out to the installed ``alembic`` CLI rather than
importing the runtime because env.py performs side effects at module
load.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_DIR = _REPO_ROOT / "backend"


def _alembic_bin() -> str:
    """Return the alembic CLI path that lives in the active interpreter's env."""
    candidate = Path(sys.executable).parent / "alembic"
    if not candidate.exists():
        pytest.skip(f"alembic CLI not found at {candidate}")
    return str(candidate)


def _run_alembic(args: list[str], db_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_alembic_bin(), *args],
        cwd=_BACKEND_DIR,
        env={
            **__import__("os").environ,
            "DATABASE_URL": db_url,
            # Defensive: make sure pytest's COMPLIANCE_SIGNING_KEY override
            # doesn't pollute alembic's settings load.
            "COMPLIANCE_SIGNING_KEY": "phase6b-test",
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def _sqlite_url(tmp_path: Path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'phase6b.sqlite'}"


# ---------------------------------------------------------------------------
# Basic CLI smoke
# ---------------------------------------------------------------------------


def test_alembic_history_includes_initial_migration(tmp_path):
    res = _run_alembic(["history"], _sqlite_url(tmp_path))
    assert res.returncode == 0, res.stderr
    assert "0001_initial" in res.stdout
    # Initial migration's down_revision is empty/None.
    assert "Initial schema (Phase 6B)" in res.stdout or "initial" in res.stdout.lower()


def test_alembic_current_on_fresh_db_is_empty(tmp_path):
    res = _run_alembic(["current"], _sqlite_url(tmp_path))
    assert res.returncode == 0, res.stderr
    # No revision applied yet — alembic prints just an info banner.
    assert "(head)" not in res.stdout


# ---------------------------------------------------------------------------
# Upgrade / downgrade lifecycle
# ---------------------------------------------------------------------------


def test_alembic_upgrade_head_then_current_reports_head(tmp_path):
    """Phase 8D bumped the head from 0001_initial → 0002_phase8d_recovery
    (the recovery_metadata column). The invariant we still pin is that
    ``alembic upgrade head`` succeeds and ``alembic current`` reports
    *some* revision tagged ``(head)`` — not the specific revision id
    (that drifts on every additive migration)."""
    db_url = _sqlite_url(tmp_path)
    up = _run_alembic(["upgrade", "head"], db_url)
    assert up.returncode == 0, up.stderr
    cur = _run_alembic(["current"], db_url)
    assert cur.returncode == 0, cur.stderr
    assert "(head)" in cur.stdout


def test_alembic_downgrade_base_drops_tables(tmp_path):
    db_url = _sqlite_url(tmp_path)
    assert _run_alembic(["upgrade", "head"], db_url).returncode == 0
    down = _run_alembic(["downgrade", "base"], db_url)
    assert down.returncode == 0, down.stderr
    # After downgrade base, current reports nothing.
    cur = _run_alembic(["current"], db_url)
    assert "(head)" not in cur.stdout


# ---------------------------------------------------------------------------
# Drift guard — autogenerate against Base.metadata must be a no-op.
# ---------------------------------------------------------------------------


def test_autogenerate_against_head_yields_no_drift(tmp_path):
    """If a model adds a column without a migration, this test fails.

    We upgrade to head against a fresh SQLite DB, then ask alembic to
    autogenerate. The resulting file's ``upgrade()`` body must be empty
    (``pass`` only) — anything else means the live ``Base.metadata`` is
    ahead of the latest migration.
    """
    db_url = _sqlite_url(tmp_path)
    assert _run_alembic(["upgrade", "head"], db_url).returncode == 0

    # Run autogenerate with a unique rev-id so we can find the file
    # deterministically.
    rev_id = "_drift_probe_phase6b"
    res = _run_alembic(
        ["revision", "--autogenerate", "-m", "drift probe", "--rev-id", rev_id],
        db_url,
    )
    assert res.returncode == 0, res.stderr

    # Locate the file via the rev-id suffix.
    versions = _BACKEND_DIR / "alembic" / "versions"
    candidates = list(versions.glob(f"{rev_id}*.py"))
    try:
        assert len(candidates) == 1, f"unexpected probe files: {candidates}"
        text = candidates[0].read_text(encoding="utf-8")
        # Extract just the upgrade body.
        m = re.search(r"def upgrade\(\) -> None:\s*(.*?)\ndef downgrade", text, re.DOTALL)
        assert m, "could not find upgrade() body in probe file"
        body = m.group(1).strip()
        # Strip Alembic's autogen banner so we compare just the ops.
        body_no_comments = "\n".join(
            line for line in body.splitlines() if not line.strip().startswith("#")
        ).strip()
        assert body_no_comments == "pass", (
            "alembic detected schema drift between models and the latest "
            "migration. Run `make db-migrate MSG=\"…\"` to capture the "
            f"change.\nProbe upgrade body:\n{body}"
        )
    finally:
        for p in candidates:
            p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# env.py exposes the live Base.metadata for autogenerate.
# ---------------------------------------------------------------------------


def test_env_target_metadata_lists_all_models():
    """Defensive: importing alembic/env.py would run migrations, so we
    just import Base.metadata directly and confirm the same four tables
    the migration creates are registered."""
    from app.models import Base

    tables = set(Base.metadata.tables.keys())
    assert {"jobs", "stage_runs", "compliance_events", "artifacts"}.issubset(tables)
    # Phase 4F-2 column should be present on jobs.
    assert "provider_selection" in Base.metadata.tables["jobs"].columns
    # Phase 3E columns on artifacts.
    assert "width" in Base.metadata.tables["artifacts"].columns
    assert "height" in Base.metadata.tables["artifacts"].columns
