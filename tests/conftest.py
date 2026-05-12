"""Root pytest conftest.

Sets test-mode environment variables and, where strictly necessary, adjusts
``sys.path`` so the test process can import code that isn't yet packaged as
a proper pip-installable distribution.

Packaging story (as of Phase 2 cleanup):

- ``common``  — installable; ``pip install -e ./common`` exposes it normally.
- ``app.*``  — backend installs editable; ``pip install -e ./backend[dev]``
  exposes it. The fallback ``sys.path`` entry below is kept only to make
  ``pytest`` work in a fresh checkout where backend hasn't been installed
  yet (e.g., immediately after ``git clone``).
- ``agents.*`` — **not yet a proper top-level pip package** (see
  ``agents/orchestrator/README.md`` for the Phase 3 cleanup note). The
  ``sys.path`` entry below is the only thing that makes ``import
  agents.compliance_officer`` work in this repo today.

Removing the ``agents`` ``sys.path`` entry requires restructuring
``agents/`` so it installs as a real ``agents`` package; that is tracked as
a Phase 3 task and intentionally out of scope here.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# --- Test environment -------------------------------------------------------
# In-memory SQLite via aiosqlite. Self-contained: no Docker, no Postgres.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("COMPLIANCE_SIGNING_KEY", "phase2-test-key-not-for-prod")

# --- PYTHONPATH (minimal) ---------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent

# Project root — only used so `agents.*` resolves. See module docstring.
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# `backend/` fallback for fresh checkouts; harmless when backend is
# already installed editable, since the installed location wins.
if str(_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(_ROOT / "backend"))
