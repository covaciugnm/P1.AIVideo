"""Root pytest conftest.

As of Phase 3F packaging cleanup, every project module is reachable via
real ``pip install -e`` of the three subprojects:

    pip install -e ./common
    pip install -e ./backend[dev]
    pip install -e ./agents[dev]

That makes ``common.*``, ``app.*``, and ``agents.*`` importable from any
process — no ``sys.path`` injection required, including from subprocesses
spawned by the test suite.

This conftest therefore deliberately does NOT touch ``sys.path``. If you
land here after seeing an ``ImportError`` for ``app.*`` or ``agents.*``,
the fix is to run the editable installs above (see
``docs/runbooks/dev-setup.md``).

We still set a few test-mode environment defaults so the backend's
pydantic Settings reads a SQLite in-memory URL and a fixed test signing
key.
"""
from __future__ import annotations

import os

# --- Test environment -------------------------------------------------------
# In-memory SQLite via aiosqlite — keeps tests self-contained.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("COMPLIANCE_SIGNING_KEY", "phase2-test-key-not-for-prod")
