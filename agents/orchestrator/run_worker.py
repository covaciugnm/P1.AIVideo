"""Phase 10A-1 — real DAG worker entrypoint for Docker light.

Replaces (or runs alongside) ``light_idle.py``. The container that runs
this module:

1. Imports the agent tree (same boot-time smoke as light_idle).
2. Opens an async SQLAlchemy engine via ``app.core.db``.
3. Polls the ``jobs`` table for rows in ``pending_compliance`` status
   (the state every newly-created job lands in — see
   ``backend/app/services/job_service.py``). Pending jobs were never
   processed before this phase because the orchestrator container ran
   ``light_idle.py``, which just idles.
4. Runs the full ``DagRunner`` against each pending job, one at a time.
   The DAG is intentionally serial — each job touches DB rows and on-
   disk artifacts, so processing one at a time is the correct safety
   posture for the default light backend.
5. Sleeps ``ORCHESTRATOR_POLL_INTERVAL_SECONDS`` between sweeps.
6. Never crashes the loop on a per-job failure: a stage rejection /
   unexpected exception is logged, the job is left in whatever state
   the DAG runner moved it into, and the loop continues.

Safety contract:

- No GPU required. ``DagRunner`` already returns categorised soft-noops
  for missing Piper / SadTalker / Ollama runtime — Phase 9B/9D removed
  every fake-media path, so an unconfigured runtime cannot pretend to
  succeed.
- No model auto-download. The worker never reaches for weights.
- No DB writes outside of what existing services + the DAG runner do.
- ``ORCHESTRATOR_MODE`` env decides behavior:
    * unset / ``worker`` (default) — real polling worker described above
    * ``idle`` — fall back to the legacy import-only smoke (light_idle).
- ``ORCHESTRATOR_DISABLE`` env (any truthy value) skips both modes — the
  container just waits for SIGTERM. Useful for ops who want the
  service stopped but the container alive.

The legacy ``agents/orchestrator/light_idle.py`` stays in the image as
the import-smoke target. Tests that exercised it keep working unchanged.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import uuid
from importlib import import_module
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

log = logging.getLogger("agents.orchestrator.run_worker")


# Same module-import smoke as light_idle.py. If the image is broken,
# fail fast so compose marks the container unhealthy.
_REQUIRED_MODULES: tuple[str, ...] = (
    "common.enums",
    "common.schemas",
    "common.path_safety",
    "common.image_validation",
    "common.audio_validation",
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
    "app.models.job",
    "app.models.compliance",
    "app.services",
)


def _setup_logging() -> None:
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )


def _verify_imports() -> None:
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


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        v = int(raw)
        return v if v > 0 else default
    except ValueError:
        return default


def _build_runner_config():
    """Use the same compliance signing key + lipsync backend the backend
    container uses, sourced through ``app.core.config.settings`` which
    reads the same .env."""
    from app.core.config import settings
    from agents.orchestrator.dag import DagRunnerConfig

    return DagRunnerConfig(
        signing_key=settings.compliance_signing_key,
        allowed_lipsync_backend=settings.allowed_lipsync_backend,
        token_ttl_seconds=settings.compliance_token_ttl_seconds,
    )


async def _list_pending_job_ids(
    sm: async_sessionmaker[AsyncSession], limit: int = 8
) -> list[uuid.UUID]:
    """Return the next batch of jobs the worker should process.

    Phase 21 — atomically CLAIM each row via ``SELECT ... FOR UPDATE
    SKIP LOCKED``. Without this, the 8 agent containers (each running
    their own ``run_worker``) all picked up the same pending jobs in
    parallel; the DAG then ran multiple times against the same job
    and concurrent FLUX/TTS calls flooded the wrappers (cache misses,
    GPU OOM, timeouts). The claim flips status to ``running`` inside
    the same transaction so any sibling worker that races us skips
    the row.

    The DAG runner itself drives jobs from ``running`` all the way to
    a terminal state; once a job reaches ``published`` / ``rejected``
    / ``failed`` it's excluded from this query.
    """
    from app.models.job import Job, JobStatus
    from sqlalchemy import update

    async with sm() as session:
        async with session.begin():
            # 1. Pick row ids that are still pending_compliance and not
            #    held by another worker.
            subq = (
                select(Job.id)
                .where(Job.status == JobStatus.pending_compliance)
                .order_by(Job.created_at.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            ids = list((await session.execute(subq)).scalars().all())
            if not ids:
                return []
            # 2. Flip to ``accepted`` so the rows become invisible to
            #    siblings (they filter on status=pending_compliance).
            # ``accepted`` is the normal post-policy-gate state, and
            # the DAG runner is happy to (re-)set it.
            await session.execute(
                update(Job)
                .where(Job.id.in_(ids))
                .values(status=JobStatus.accepted)
            )
        return ids


async def _process_one(
    job_id: uuid.UUID,
    sm: async_sessionmaker[AsyncSession],
    runner_config,
) -> dict[str, Any]:
    """Run the DAG against a single job. Catches every exception so a
    single bad job cannot kill the worker loop."""
    from agents.orchestrator.dag import DagRunner

    log.info("orchestrator: starting job %s", job_id)
    try:
        runner = DagRunner(sm, runner_config)
        final = await runner.run(job_id)
        log.info("orchestrator: job %s reached %s", job_id, final.value)
        return {"job_id": str(job_id), "ok": True, "final_status": final.value}
    except Exception as exc:  # noqa: BLE001 — top-of-loop guard
        log.exception("orchestrator: job %s raised %s", job_id, type(exc).__name__)
        return {
            "job_id": str(job_id),
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


async def _run_worker_loop() -> None:
    from app.core import db as core_db

    poll_seconds = _int_env("ORCHESTRATOR_POLL_INTERVAL_SECONDS", 5)
    batch_size = _int_env("ORCHESTRATOR_BATCH_SIZE", 8)
    max_iterations = _int_env("ORCHESTRATOR_MAX_ITERATIONS", 0)  # 0 = forever
    burst_drain = _bool_env("ORCHESTRATOR_BURST_DRAIN_ON_START", True)

    await core_db.init_db()
    sm = core_db.get_sessionmaker()
    runner_config = _build_runner_config()

    stop_event = asyncio.Event()

    def _on_sig(signum: int, _frame: object) -> None:
        log.info("received signal %d; stopping worker after current job", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, _on_sig)
    signal.signal(signal.SIGINT, _on_sig)

    log.info(
        "worker ready (poll_interval=%ss, batch_size=%s, burst_drain=%s)",
        poll_seconds,
        batch_size,
        burst_drain,
    )

    iteration = 0
    while not stop_event.is_set():
        iteration += 1
        if max_iterations and iteration > max_iterations:
            log.info("ORCHESTRATOR_MAX_ITERATIONS reached; exiting cleanly")
            break

        ids = await _list_pending_job_ids(sm, limit=batch_size)
        if ids:
            log.info("orchestrator: %d pending job(s) to process", len(ids))
            for jid in ids:
                if stop_event.is_set():
                    log.info("stop requested mid-batch; deferring remaining jobs")
                    break
                await _process_one(jid, sm, runner_config)
            if burst_drain and not stop_event.is_set():
                # If we just drained a batch, immediately probe for more
                # so the worker catches jobs that the backend queues
                # while we were running.
                continue
        else:
            log.debug("orchestrator: no pending jobs; sleeping")

        # Sleep, but wake on SIGTERM.
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
        except asyncio.TimeoutError:
            pass

    log.info("worker loop exiting")
    try:
        await core_db.async_reset_engine()
    except Exception:
        log.debug("engine dispose raised; ignoring", exc_info=True)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def _run_idle_fallback() -> None:
    """Re-use the legacy idle behavior. Imported lazily so the worker
    path stays fast."""
    from agents.orchestrator import light_idle

    light_idle.main()


def main() -> None:
    _setup_logging()
    log.info("Phase 10A-1 orchestrator entrypoint starting")
    _verify_imports()

    if _bool_env("ORCHESTRATOR_DISABLE", default=False):
        log.warning(
            "ORCHESTRATOR_DISABLE=true — neither worker nor idle smoke will run; "
            "waiting for SIGTERM"
        )
        stop = asyncio.Event()
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        asyncio.run(stop.wait())
        return

    mode = (os.environ.get("ORCHESTRATOR_MODE") or "worker").strip().lower()
    if mode == "idle":
        log.info("ORCHESTRATOR_MODE=idle — falling back to legacy import-only smoke")
        _run_idle_fallback()
        return
    if mode != "worker":
        log.warning("unknown ORCHESTRATOR_MODE=%r; defaulting to 'worker'", mode)

    asyncio.run(_run_worker_loop())


if __name__ == "__main__":
    main()
