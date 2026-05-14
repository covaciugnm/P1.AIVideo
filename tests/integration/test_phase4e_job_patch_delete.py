"""Phase 4E integration tests — PATCH + DELETE /api/v1/jobs/{id}.

Boundary expectations:
- Metadata-only: no media touched, no binary in responses.
- PATCH refuses immutable-field edits past pending_compliance.
- PATCH refuses any edit once the job is in a terminal status.
- DELETE cascades stage_runs / compliance_events / artifacts via the
  ON DELETE CASCADE FK (SQLite needs PRAGMA foreign_keys=ON; the engine
  setup in app.core.db enables it).
- 404 on unknown ids.
- Endpoints resolve under both /jobs/{id} and /api/v1/jobs/{id}.
"""
from __future__ import annotations

import uuid

import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def app_under_test(monkeypatch, tmp_path):
    monkeypatch.setenv("PROVIDED_AUDIO_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("PROVIDED_IMAGE_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("SCRIPTWRITER_BACKEND", "template")

    from app.core import db as core_db
    from app.main import create_app
    from app.services import queue_publisher

    await core_db.async_reset_engine()
    await core_db.init_db()

    fake = fakeaioredis.FakeRedis(decode_responses=True)
    queue_publisher.set_redis_client(fake)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    await fake.aclose()
    queue_publisher.reset_redis_client()
    await core_db.async_reset_engine()


def _valid_payload(brief: str = "Initial brief.") -> dict:
    return {
        "brief": brief,
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "target_duration_seconds": 30,
        "watermark_required": True,
        "c2pa_required": True,
        "script_text": "Tip one: avoid screens.",
    }


async def _create_pending_job(client) -> uuid.UUID:
    r = await client.post("/api/v1/jobs", json=_valid_payload())
    assert r.status_code == 201, r.text
    return uuid.UUID(r.json()["id"])


async def _create_and_run_job(client) -> uuid.UUID:
    from agents.orchestrator.dag import DagRunner, DagRunnerConfig
    from app.core.db import get_sessionmaker

    job_id = await _create_pending_job(client)
    cfg = DagRunnerConfig(
        signing_key="phase4e-test-key",
        allowed_lipsync_backend="sadtalker",
        token_ttl_seconds=3600,
    )
    await DagRunner(get_sessionmaker(), cfg).run(job_id)
    return job_id


# ---------------------------------------------------------------------------
# PATCH happy path
# ---------------------------------------------------------------------------


async def test_patch_brief_on_pending_job_succeeds(app_under_test):
    job_id = await _create_pending_job(app_under_test)
    r = await app_under_test.patch(
        f"/api/v1/jobs/{job_id}", json={"brief": "edited brief"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["brief"] == "edited brief"


async def test_patch_multiple_fields_on_pending_job(app_under_test):
    job_id = await _create_pending_job(app_under_test)
    r = await app_under_test.patch(
        f"/api/v1/jobs/{job_id}",
        json={
            "brief": "new brief",
            "target_duration_seconds": 45,
            "script_text": "Edited script body.",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["brief"] == "new brief"
    assert body["target_duration_seconds"] == 45
    assert body["script_text"] == "Edited script body."


# ---------------------------------------------------------------------------
# PATCH rejections
# ---------------------------------------------------------------------------


async def test_patch_empty_body_rejected(app_under_test):
    job_id = await _create_pending_job(app_under_test)
    r = await app_under_test.patch(f"/api/v1/jobs/{job_id}", json={})
    assert r.status_code == 400
    assert "no editable fields" in r.json()["detail"]


async def test_patch_unknown_field_rejected_by_schema(app_under_test):
    job_id = await _create_pending_job(app_under_test)
    # ``status`` is not in JobUpdateRequest's allowed fields; schema's
    # ``extra="forbid"`` produces a 422.
    r = await app_under_test.patch(
        f"/api/v1/jobs/{job_id}", json={"status": "accepted"}
    )
    assert r.status_code == 422


async def test_patch_duration_out_of_bounds_rejected(app_under_test):
    job_id = await _create_pending_job(app_under_test)
    r = await app_under_test.patch(
        f"/api/v1/jobs/{job_id}", json={"target_duration_seconds": 1}
    )
    assert r.status_code == 422


async def test_patch_watermark_false_rejected(app_under_test):
    job_id = await _create_pending_job(app_under_test)
    r = await app_under_test.patch(
        f"/api/v1/jobs/{job_id}", json={"watermark_required": False}
    )
    assert r.status_code == 422


async def test_patch_404_on_unknown_id(app_under_test):
    missing = uuid.uuid4()
    r = await app_under_test.patch(f"/api/v1/jobs/{missing}", json={"brief": "x"})
    assert r.status_code == 404


async def test_patch_rejected_after_pipeline_runs(app_under_test):
    job_id = await _create_and_run_job(app_under_test)
    # After the DAG, the job is published. Brief edits are blocked.
    r = await app_under_test.patch(
        f"/api/v1/jobs/{job_id}", json={"brief": "should not apply"}
    )
    assert r.status_code == 409
    assert "terminal state" in r.json()["detail"]


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


async def test_delete_pending_job_succeeds(app_under_test):
    job_id = await _create_pending_job(app_under_test)
    r = await app_under_test.delete(f"/api/v1/jobs/{job_id}")
    assert r.status_code == 204
    # The job is gone.
    r2 = await app_under_test.get(f"/api/v1/jobs/{job_id}")
    assert r2.status_code == 404


async def test_delete_404_on_unknown_id(app_under_test):
    missing = uuid.uuid4()
    r = await app_under_test.delete(f"/api/v1/jobs/{missing}")
    assert r.status_code == 404


async def test_delete_cascades_stage_runs_and_artifacts(app_under_test):
    job_id = await _create_and_run_job(app_under_test)

    # Sanity: the job has stage runs + artifacts before we delete it.
    progress = (await app_under_test.get(f"/api/v1/jobs/{job_id}/progress")).json()
    assert progress["completed_stages"] > 0
    artifacts = (await app_under_test.get(f"/api/v1/jobs/{job_id}/artifacts")).json()
    assert len(artifacts) > 0

    r = await app_under_test.delete(f"/api/v1/jobs/{job_id}")
    assert r.status_code == 204

    # Job is gone — and the cascading reads from the now-missing job
    # return 404 cleanly (no orphaned rows surfacing through the API).
    for sub in ("progress", "timeline", "artifacts", "compliance-events"):
        r = await app_under_test.get(f"/api/v1/jobs/{job_id}/{sub}")
        assert r.status_code == 404, sub


# ---------------------------------------------------------------------------
# Alias coverage: /jobs/{id} and /api/v1/jobs/{id} must both PATCH + DELETE
# ---------------------------------------------------------------------------


async def test_patch_delete_resolve_on_legacy_prefix(app_under_test):
    job_id = await _create_pending_job(app_under_test)
    r = await app_under_test.patch(
        f"/jobs/{job_id}", json={"brief": "via legacy prefix"}
    )
    assert r.status_code == 200
    assert r.json()["brief"] == "via legacy prefix"

    r2 = await app_under_test.delete(f"/jobs/{job_id}")
    assert r2.status_code == 204
