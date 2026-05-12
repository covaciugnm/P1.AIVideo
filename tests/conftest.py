"""Root pytest conftest.

Sets environment variables and PYTHONPATH BEFORE any app/agent module is
imported so:
- the backend's pydantic Settings read the test DATABASE_URL,
- the test file can `import app.*` and `import agents.*` without a venv
  install step (useful when iterating without `pip install -e`).

This file runs once per pytest session, before any test or fixture is
collected, so env-var ordering is well-defined.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# --- Test environment -------------------------------------------------------
# In-memory SQLite via aiosqlite. Keeps the test self-contained — no Docker,
# no Postgres install required.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")

# --- PYTHONPATH -------------------------------------------------------------
# Project root → makes `agents.*` importable.
# `backend/` → makes `app.*` importable.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))
