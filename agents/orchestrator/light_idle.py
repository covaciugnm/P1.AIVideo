"""Phase 4C light-runtime idle launcher.

The full orchestrator worker isn't shipped yet — message-consuming +
DAG-driving logic is in ``agents/orchestrator/orchestrator.py`` and
``agents/orchestrator/dag.py``, but neither has a ``__main__`` entrypoint
and Phase 4C's boundary is metadata-only.

This launcher just imports every agent package at startup (so the image's
install graph is verified end-to-end), logs a single ready line, and then
idles forever. Compose can keep the service alive without any side-effects.

A real worker entrypoint will replace this in a later phase.
"""
from __future__ import annotations

import logging
import os
import signal
import sys
import time
from importlib import import_module

# Modules to verify at startup. Failure to import any of them is a hard fail
# so Compose marks the container unhealthy and a developer notices.
_REQUIRED_MODULES: tuple[str, ...] = (
    # common (path dependency)
    "common.enums",
    "common.schemas",
    "common.path_safety",
    "common.image_validation",
    "common.audio_validation",
    # agents tree
    "agents",
    "agents.orchestrator",
    "agents.orchestrator.dag",
    "agents.orchestrator.handlers",
    "agents.orchestrator.orchestrator",
    "agents.scriptwriter",
    "agents.voice",
    "agents.face",
    "agents.editor",
    "agents.qc",
    "agents.publisher",
    "agents.lipsync",
    "agents.compliance_officer",
    # backend coupling (Phase 4C compat): orchestrator handlers import
    # app.models / app.services. Validate that too.
    "app.models.job",
    "app.models.compliance",
    "app.services",
)


def _setup_logging() -> logging.Logger:
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    return logging.getLogger("agents.orchestrator.light_idle")


def _verify_imports(log: logging.Logger) -> None:
    failures: list[tuple[str, str]] = []
    for name in _REQUIRED_MODULES:
        try:
            import_module(name)
        except Exception as exc:  # pragma: no cover — startup-only
            failures.append((name, f"{type(exc).__name__}: {exc}"))
    if failures:
        for name, err in failures:
            log.error("module import failed: %s — %s", name, err)
        sys.exit(1)
    log.info("all %d required modules imported OK", len(_REQUIRED_MODULES))


def main() -> None:
    log = _setup_logging()
    log.info("Phase 4C light idle launcher starting (metadata-only mode)")
    _verify_imports(log)
    log.info(
        "ready — no real worker logic runs in Phase 4C; container will idle "
        "until SIGTERM/SIGINT"
    )

    stop = False

    def _signal_handler(signum: int, _frame: object) -> None:
        nonlocal stop
        log.info("received signal %d; shutting down idle loop", signum)
        stop = True

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    while not stop:
        time.sleep(60)


if __name__ == "__main__":
    main()
