"""Phase 8D — job cancel + retry + recovery metadata.

What this phase pins:

- ``jobs.recovery_metadata`` JSON column is plumbed end-to-end (model
  → API response).
- ``POST /jobs/{id}/cancel``:
  - 404 on unknown job.
  - 409 on terminal jobs (published / rejected / failed).
  - Non-terminal → status flips to ``rejected``, ``rejection_reason``
    documents the cancellation, ``recovery_metadata.cancelled_at`` +
    ``cancellation_reason`` populated, compliance event recorded.
  - Mirror route under ``/api/v1/jobs/...`` works (Phase 4B alias).
- ``POST /jobs/{id}/retry``:
  - 404 on unknown job.
  - 409 on non-terminal jobs (pending_compliance / accepted) AND on
    ``published`` (only failed / rejected may retry).
  - failed / rejected → ``retry_count`` increments, ``retry_requested_at``
    set, compliance event recorded. History (stage_runs, prior
    artifacts) preserved.
- Recovery metadata persists across multiple retries (counter rises).
- Module-load isolation unchanged (no torch).
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


@pytest_asyncio.fixture
async def app_under_test(monkeypatch, tmp_path):
    monkeypatch.setenv("UPLOAD_AUDIO_ROOT", str(tmp_path / "audio"))
    monkeypatch.setenv("UPLOAD_IMAGE_ROOT", str(tmp_path / "images"))
    monkeypatch.setenv("UPLOAD_TEXT_ROOT", str(tmp_path / "text"))
    monkeypatch.setenv("SCRIPTWRITER_BACKEND", "template")

    from app.core import db as core_db
    from app.main import create_app
    from app.services import queue_publisher

    await core_db.async_reset_engine()
    await core_db.init_db()
    fake = fakeaioredis.FakeRedis(decode_responses=True)
    queue_publisher.set_redis_client(fake)
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
    await fake.aclose()
    queue_publisher.reset_redis_client()
    await core_db.async_reset_engine()


async def _create_job(client: AsyncClient) -> str:
    r = await client.post(
        "/api/v1/jobs",
        json={
            "brief": "phase 8d",
            "synthetic_person_confirmed": True,
            "consent_confirmed": True,
            "target_duration_seconds": 30,
            "watermark_required": True,
            "c2pa_required": True,
            "script_text": "phase 8d",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _force_job_status(job_id: str, status: str) -> None:
    """Directly flip a job into a terminal status — the API doesn't
    expose this transition for security, but tests need it."""
    from app.core.db import get_sessionmaker
    from app.models.job import Job, JobStatus

    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(select(Job).where(Job.id == uuid.UUID(job_id)))
        job = result.scalar_one()
        job.status = JobStatus(status)
        await session.commit()


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


async def test_cancel_unknown_job_returns_404(app_under_test):
    r = await app_under_test.post(
        f"/api/v1/jobs/{uuid.uuid4()}/cancel", json={}
    )
    assert r.status_code == 404


async def test_cancel_pending_job_marks_rejected_and_records_metadata(app_under_test):
    job_id = await _create_job(app_under_test)
    r = await app_under_test.post(
        f"/api/v1/jobs/{job_id}/cancel",
        json={"reason": "operator changed their mind"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "rejected"
    assert "operator changed their mind" in body["rejection_reason"]
    rm = body["recovery_metadata"]
    assert rm is not None
    assert "cancelled_at" in rm
    assert rm["cancellation_reason"] == "operator changed their mind"

    # Compliance event written.
    from app.core.db import get_sessionmaker
    from app.models.compliance import ComplianceEvent

    sm = get_sessionmaker()
    async with sm() as session:
        events = (
            await session.execute(
                select(ComplianceEvent).where(
                    ComplianceEvent.job_id == uuid.UUID(job_id),
                    ComplianceEvent.gate == "job_cancel",
                )
            )
        ).scalars().all()
        assert len(events) == 1
        assert events[0].decision.value == "reject"


async def test_cancel_terminal_job_returns_409(app_under_test):
    job_id = await _create_job(app_under_test)
    await _force_job_status(job_id, "published")
    r = await app_under_test.post(
        f"/api/v1/jobs/{job_id}/cancel", json={"reason": "too late"}
    )
    assert r.status_code == 409


async def test_cancel_rejects_unknown_fields(app_under_test):
    job_id = await _create_job(app_under_test)
    r = await app_under_test.post(
        f"/api/v1/jobs/{job_id}/cancel", json={"unknown": "x"}
    )
    assert r.status_code == 422


async def test_cancel_default_reason_when_none_provided(app_under_test):
    job_id = await _create_job(app_under_test)
    r = await app_under_test.post(f"/api/v1/jobs/{job_id}/cancel", json={})
    body = r.json()
    assert "cancelled by operator" in body["rejection_reason"]


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------


async def test_retry_unknown_job_returns_404(app_under_test):
    r = await app_under_test.post(
        f"/api/v1/jobs/{uuid.uuid4()}/retry", json={}
    )
    assert r.status_code == 404


async def test_retry_non_terminal_job_returns_409(app_under_test):
    job_id = await _create_job(app_under_test)
    r = await app_under_test.post(f"/api/v1/jobs/{job_id}/retry", json={})
    assert r.status_code == 409


async def test_retry_published_job_returns_409(app_under_test):
    """Retry is only for failed/rejected; published is a success path."""
    job_id = await _create_job(app_under_test)
    await _force_job_status(job_id, "published")
    r = await app_under_test.post(f"/api/v1/jobs/{job_id}/retry", json={})
    assert r.status_code == 409


async def test_retry_failed_job_records_metadata(app_under_test):
    job_id = await _create_job(app_under_test)
    await _force_job_status(job_id, "failed")
    r = await app_under_test.post(
        f"/api/v1/jobs/{job_id}/retry",
        json={"reason": "transient error", "stage_name": "lipsync"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Retry does NOT change job.status — the worker picks up the
    # retry_requested_at marker later.
    assert body["status"] == "failed"
    rm = body["recovery_metadata"]
    assert rm["retry_count"] == 1
    assert "retry_requested_at" in rm
    assert rm["retry_stage_name"] == "lipsync"
    assert rm["retry_reason"] == "transient error"

    # Compliance event written.
    from app.core.db import get_sessionmaker
    from app.models.compliance import ComplianceEvent

    sm = get_sessionmaker()
    async with sm() as session:
        events = (
            await session.execute(
                select(ComplianceEvent).where(
                    ComplianceEvent.job_id == uuid.UUID(job_id),
                    ComplianceEvent.gate == "job_retry",
                )
            )
        ).scalars().all()
        assert len(events) == 1


async def test_retry_increments_counter_across_calls(app_under_test):
    job_id = await _create_job(app_under_test)
    await _force_job_status(job_id, "failed")
    r1 = await app_under_test.post(f"/api/v1/jobs/{job_id}/retry", json={})
    assert r1.json()["recovery_metadata"]["retry_count"] == 1
    r2 = await app_under_test.post(f"/api/v1/jobs/{job_id}/retry", json={})
    assert r2.json()["recovery_metadata"]["retry_count"] == 2
    r3 = await app_under_test.post(f"/api/v1/jobs/{job_id}/retry", json={})
    assert r3.json()["recovery_metadata"]["retry_count"] == 3


async def test_retry_preserves_history(app_under_test):
    """Retrying must not delete stage_runs or artifacts."""
    job_id = await _create_job(app_under_test)
    from app.core.db import get_sessionmaker
    from app.services import artifact_service

    sm = get_sessionmaker()
    async with sm() as session:
        await artifact_service.register_artifact(
            session,
            job_id=uuid.UUID(job_id),
            artifact_type="audio",
            uri="file:///tmp/x.wav",
            local_path="/tmp/x.wav",
            mime_type="audio/wav",
        )
        await session.commit()

    await _force_job_status(job_id, "rejected")
    await app_under_test.post(f"/api/v1/jobs/{job_id}/retry", json={})

    # Verify the audio artifact still exists.
    from app.models.artifact import Artifact

    async with sm() as session:
        rows = (
            await session.execute(
                select(Artifact).where(Artifact.job_id == uuid.UUID(job_id))
            )
        ).scalars().all()
        assert any(a.artifact_type == "audio" for a in rows)


# ---------------------------------------------------------------------------
# Alias mirror: /jobs/... AND /api/v1/jobs/... both work
# ---------------------------------------------------------------------------


async def test_cancel_works_under_legacy_jobs_prefix(app_under_test):
    job_id = await _create_job(app_under_test)
    r = await app_under_test.post(f"/jobs/{job_id}/cancel", json={"reason": "x"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "rejected"


async def test_retry_works_under_legacy_jobs_prefix(app_under_test):
    job_id = await _create_job(app_under_test)
    await _force_job_status(job_id, "failed")
    r = await app_under_test.post(f"/jobs/{job_id}/retry", json={})
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# JobResponse / JobDetail expose recovery_metadata cleanly
# ---------------------------------------------------------------------------


async def test_job_detail_returns_recovery_metadata(app_under_test):
    job_id = await _create_job(app_under_test)
    await app_under_test.post(
        f"/api/v1/jobs/{job_id}/cancel", json={"reason": "test"}
    )
    r = await app_under_test.get(f"/api/v1/jobs/{job_id}")
    body = r.json()
    assert body["recovery_metadata"] is not None
    assert body["recovery_metadata"]["cancellation_reason"] == "test"


# ---------------------------------------------------------------------------
# Module-load isolation invariant unchanged
# ---------------------------------------------------------------------------


def test_jobs_api_module_still_torch_free():
    import subprocess
    import sys

    code = (
        "import sys\n"
        "import app.api.jobs  # noqa: F401\n"
        "print('torch' in sys.modules)\n"
    )
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=20,
        cwd=str(Path(__file__).resolve().parents[2]),
    )
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "False"
