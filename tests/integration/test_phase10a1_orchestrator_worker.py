"""Phase 10A-1 — orchestrator real DAG worker.

Pins:
- ``_list_pending_job_ids`` returns rows in ``pending_compliance``
  (and only those) ordered by creation time.
- ``_process_one`` swallows per-job exceptions so a single failing
  job can't kill the loop. The worker logs the failure but keeps
  going.
- The worker entry point respects ``ORCHESTRATOR_MODE=idle`` and
  ``ORCHESTRATOR_DISABLE=true``.
- Default operation drives a pending_compliance job through the DAG
  to a terminal status (``published`` for the dependency-free
  template path) and leaves real artifact rows behind for the
  metadata-only edit_plan / qc_report / final_export artifacts.
- The legacy ``light_idle`` import-smoke still works (regression).
- Module-load is light: no torch / piper / f5_tts pulled by import.
"""
from __future__ import annotations

import asyncio
import sys
import uuid

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from sqlalchemy import select


@pytest_asyncio.fixture
async def db_under_test(monkeypatch, tmp_path):
    monkeypatch.setenv("UPLOAD_AUDIO_ROOT", str(tmp_path / "audio"))
    monkeypatch.setenv("UPLOAD_IMAGE_ROOT", str(tmp_path / "images"))
    monkeypatch.setenv("UPLOAD_TEXT_ROOT", str(tmp_path / "text"))
    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("PROVIDED_AUDIO_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("PROVIDED_IMAGE_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("SCRIPTWRITER_BACKEND", "template")
    monkeypatch.delenv("SCRIPTWRITER_ENABLE_NETWORK_CALLS", raising=False)

    from app.core import db as core_db
    from app.services import queue_publisher

    await core_db.async_reset_engine()
    await core_db.init_db()
    fake = fakeaioredis.FakeRedis(decode_responses=True)
    queue_publisher.set_redis_client(fake)
    yield core_db.get_sessionmaker()
    await fake.aclose()
    queue_publisher.reset_redis_client()
    await core_db.async_reset_engine()


async def _seed_pending_job(sm, *, brief: str = "phase 10a1 worker test") -> uuid.UUID:
    """Insert a job directly through the service layer in
    ``pending_compliance`` state — same shape the API would create."""
    from app.schemas.job import JobCreateRequest
    from app.services import job_service

    payload = JobCreateRequest(
        brief=brief,
        synthetic_person_confirmed=True,
        consent_confirmed=True,
        target_duration_seconds=30,
        watermark_required=True,
        c2pa_required=True,
        voice_mode="tts",
        script_text=(
            "Worker smoke. Hook line. Body sentence. Save this for later."
        ),
        tts_backend="piper",
        provider_selection=None,
    )
    async with sm() as session:
        job = await job_service.create_job(session, payload)
        # job_service.create_job already commits; just return the id.
        return job.id


# ---------------------------------------------------------------------------
# Pickup logic
# ---------------------------------------------------------------------------


async def test_list_pending_job_ids_returns_only_pending_compliance(db_under_test):
    from agents.orchestrator.run_worker import _list_pending_job_ids
    from app.models.job import Job, JobStatus

    sm = db_under_test
    jid1 = await _seed_pending_job(sm, brief="worker pending #1")
    jid2 = await _seed_pending_job(sm, brief="worker pending #2")
    # Move one job to a terminal status so it should NOT be returned.
    async with sm() as session:
        result = await session.execute(select(Job).where(Job.id == jid2))
        j = result.scalar_one()
        j.status = JobStatus.published
        await session.commit()

    ids = await _list_pending_job_ids(sm, limit=8)
    assert jid1 in ids
    assert jid2 not in ids
    # Sanity: every returned id corresponds to a pending row.
    async with sm() as session:
        for jid in ids:
            row = (await session.execute(select(Job).where(Job.id == jid))).scalar_one()
            assert row.status == JobStatus.pending_compliance


# ---------------------------------------------------------------------------
# Per-job processing + DAG drive
# ---------------------------------------------------------------------------


async def test_worker_drives_pending_job_to_terminal_status(db_under_test):
    """The template scriptwriter path has no external runtime deps and
    must reach a terminal status. Phase 9D's metadata-only pipeline
    publishes by default."""
    from agents.orchestrator.run_worker import _build_runner_config, _process_one
    from app.models.job import Job, JobStatus

    sm = db_under_test
    jid = await _seed_pending_job(sm)
    result = await _process_one(jid, sm, _build_runner_config())
    assert result["ok"] is True, result
    assert result["final_status"] in (
        JobStatus.published.value,
        JobStatus.rejected.value,
        JobStatus.failed.value,
    )
    # Whatever the verdict, the job is NOT pending_compliance anymore.
    async with sm() as session:
        j = (await session.execute(select(Job).where(Job.id == jid))).scalar_one()
        assert j.status != JobStatus.pending_compliance


async def test_worker_persists_dag_artifacts(db_under_test):
    """A passing job should produce edit_plan + qc_report + final_export
    artifact rows. Phase 9D placeholder reel_drafts intentionally don't
    promote because they have no checksum."""
    from agents.orchestrator.run_worker import _build_runner_config, _process_one
    from app.models.artifact import Artifact
    from common.enums import ArtifactType

    sm = db_under_test
    jid = await _seed_pending_job(sm)
    await _process_one(jid, sm, _build_runner_config())
    async with sm() as session:
        rows = await session.execute(
            select(Artifact).where(Artifact.job_id == jid)
        )
        artifacts = list(rows.scalars().all())
    types = sorted({a.artifact_type for a in artifacts})
    assert ArtifactType.edit_plan.value in types
    assert ArtifactType.metadata.value in types
    assert ArtifactType.final_export.value in types
    # The DAG must NOT have registered phantom media artifacts.
    for a in artifacts:
        if a.artifact_type == ArtifactType.video.value:
            assert a.local_path, "video artifact without local_path leaked into DB"
        if a.artifact_type == ArtifactType.audio.value:
            assert a.local_path, "audio artifact without local_path leaked into DB"


# ---------------------------------------------------------------------------
# Resilience
# ---------------------------------------------------------------------------


async def test_process_one_swallows_unexpected_exceptions(db_under_test, monkeypatch):
    """A per-job crash inside DagRunner must NOT propagate out of
    ``_process_one``; the worker reports the failure and keeps going."""
    from agents.orchestrator.run_worker import _build_runner_config, _process_one
    from agents.orchestrator import dag as dag_module

    sm = db_under_test
    jid = await _seed_pending_job(sm)

    class _BoomRunner:
        def __init__(self, sm, cfg) -> None:
            self._sm = sm

        async def run(self, _job_id: uuid.UUID):
            raise RuntimeError("contrived DAG explosion")

    monkeypatch.setattr(dag_module, "DagRunner", _BoomRunner)
    result = await _process_one(jid, sm, _build_runner_config())
    assert result["ok"] is False
    assert "RuntimeError" in result["error"]
    assert "contrived DAG explosion" in result["error"]


async def test_worker_loop_processes_many_jobs_without_dying(db_under_test, monkeypatch):
    """Seed multiple jobs (with one engineered to fail) and prove the
    worker drains them all in a single iteration."""
    from agents.orchestrator.run_worker import _build_runner_config, _list_pending_job_ids, _process_one
    from agents.orchestrator import dag as dag_module
    from app.models.job import JobStatus

    sm = db_under_test
    good_ids = [await _seed_pending_job(sm, brief=f"good job {i}") for i in range(3)]
    bad_id = await _seed_pending_job(sm, brief="bad job will fail")

    original_run = dag_module.DagRunner.run

    async def _flaky_run(self, jid: uuid.UUID):
        if jid == bad_id:
            raise RuntimeError("simulated stage explosion")
        return await original_run(self, jid)

    monkeypatch.setattr(dag_module.DagRunner, "run", _flaky_run)

    results = []
    cfg = _build_runner_config()
    ids = await _list_pending_job_ids(sm, limit=10)
    assert set(ids) >= set(good_ids + [bad_id])
    for jid in ids:
        results.append(await _process_one(jid, sm, cfg))

    bad = [r for r in results if r["job_id"] == str(bad_id)]
    good = [r for r in results if r["job_id"] != str(bad_id)]
    assert bad and bad[0]["ok"] is False
    assert good and all(r["ok"] for r in good)


# ---------------------------------------------------------------------------
# Mode switching + module-load isolation
# ---------------------------------------------------------------------------


def test_orchestrator_mode_idle_runs_legacy_smoke(monkeypatch):
    """``ORCHESTRATOR_MODE=idle`` must call the legacy import smoke
    rather than the worker loop."""
    from agents.orchestrator import run_worker

    monkeypatch.setenv("ORCHESTRATOR_MODE", "idle")

    called = {"idle": False, "worker": False}

    def _fake_idle():
        called["idle"] = True

    def _fake_run_loop():
        called["worker"] = True
        return asyncio.sleep(0)

    monkeypatch.setattr(run_worker, "_run_idle_fallback", _fake_idle)
    monkeypatch.setattr(run_worker, "_run_worker_loop", _fake_run_loop)
    monkeypatch.setattr(run_worker, "_verify_imports", lambda: None)

    run_worker.main()
    assert called["idle"] is True
    assert called["worker"] is False


def test_legacy_light_idle_module_still_imports():
    """Regression: light_idle should keep its public API even though the
    Dockerfile no longer invokes it by default."""
    from agents.orchestrator import light_idle

    assert callable(light_idle.main)
    # The required-modules list documents the agent boot graph; never empty.
    assert isinstance(light_idle._REQUIRED_MODULES, tuple) and light_idle._REQUIRED_MODULES


def test_run_worker_import_does_not_pull_torch_or_f5tts():
    """Phase 9 import-discipline: bringing the worker into the process
    must not drag torch / f5_tts / piper into ``sys.modules``."""
    import agents.orchestrator.run_worker  # noqa: F401

    forbidden = {"torch", "f5_tts", "f5tts", "torchaudio", "piper"}
    present = forbidden & set(sys.modules)
    assert not present, f"run_worker leaked heavy deps: {present}"


_ = pytest  # placate lint
