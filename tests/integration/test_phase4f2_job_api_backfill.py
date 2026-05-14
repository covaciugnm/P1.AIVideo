"""Phase 4F-2 — Phase 4A API completeness backfill.

Covers the five additive deltas:

1. ``GET /api/v1/jobs/{id}/summary`` combined payload.
2. ``JobSummary`` includes ``qc_passed`` + ``final_export_available``.
3. ``GET /api/v1/jobs/{id}`` returns the aggregate ``JobDetail`` shape
   (legacy fields preserved + new computed fields).
4. ``JobProgress`` includes ``pending_stages`` + the three flat
   stage-name lists.
5. ``GET /api/v1/jobs?status=`` filters by ``JobStatus`` and rejects
   invalid values with 422.

Boundary checks (regression-free):
- metadata-only — every response JSON round-trips.
- no secrets / no compliance signing key / no HMAC bytes echoed back.
- legacy ``JobResponse`` fields still present on ``GET /jobs/{id}``.
"""
from __future__ import annotations

import json
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


def _runner_config():
    from agents.orchestrator.dag import DagRunnerConfig

    return DagRunnerConfig(
        signing_key="phase4f2-test-key-not-for-prod",
        allowed_lipsync_backend="sadtalker",
        token_ttl_seconds=3600,
    )


def _valid_payload(brief: str = "Three calming bedtime habits.") -> dict:
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
    from agents.orchestrator.dag import DagRunner
    from app.core.db import get_sessionmaker

    job_id = await _create_pending_job(client)
    await DagRunner(get_sessionmaker(), _runner_config()).run(job_id)
    return job_id


# ---------------------------------------------------------------------------
# 1. /summary endpoint
# ---------------------------------------------------------------------------


async def test_summary_returns_combined_payload_for_published_job(app_under_test):
    job_id = await _create_and_run_job(app_under_test)
    r = await app_under_test.get(f"/api/v1/jobs/{job_id}/summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {
        "job",
        "progress",
        "timeline",
        "artifacts",
        "compliance_events",
        "qc_report",
        "final_export",
    }
    # The job sub-payload is the aggregate JobDetail.
    assert body["job"]["id"] == str(job_id)
    assert body["job"]["status"] == "published"
    assert body["job"]["progress_percent"] == 100.0
    assert body["job"]["artifact_count"] >= 1
    # Progress is the same as the /progress endpoint.
    assert body["progress"]["total_stages"] == 11
    assert body["progress"]["completed_stages"] == 11
    # Timeline carries the canonical 11 stage runs.
    assert len(body["timeline"]) == 11
    # QC + final-export populated for a published job.
    assert body["qc_report"] is not None
    assert body["final_export"] is not None


async def test_summary_returns_404_for_unknown_job(app_under_test):
    missing = uuid.uuid4()
    r = await app_under_test.get(f"/api/v1/jobs/{missing}/summary")
    assert r.status_code == 404


async def test_summary_for_pending_job_has_null_qc_and_final_export(app_under_test):
    job_id = await _create_pending_job(app_under_test)
    r = await app_under_test.get(f"/api/v1/jobs/{job_id}/summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["qc_report"] is None
    assert body["final_export"] is None
    assert body["job"]["progress_percent"] == 0.0
    assert body["job"]["artifact_count"] == 0


# ---------------------------------------------------------------------------
# 2. JobSummary qc_passed + final_export_available
# ---------------------------------------------------------------------------


async def test_jobs_list_summary_includes_qc_and_final_export_flags(app_under_test):
    # Mix of pending + published.
    pending_id = await _create_pending_job(app_under_test)
    done_id = await _create_and_run_job(app_under_test)

    r = await app_under_test.get("/api/v1/jobs")
    assert r.status_code == 200, r.text
    body = r.json()
    by_id = {item["id"]: item for item in body}
    assert str(pending_id) in by_id
    assert str(done_id) in by_id

    pending = by_id[str(pending_id)]
    done = by_id[str(done_id)]

    # Pending job: QC hasn't run, final_export not produced.
    assert pending["qc_passed"] is None
    assert pending["final_export_available"] is False

    # Published job: QC report stored with passed=True, final_export emitted.
    assert done["qc_passed"] is True
    assert done["final_export_available"] is True


# ---------------------------------------------------------------------------
# 3. JobDetail aggregate fields
# ---------------------------------------------------------------------------


async def test_job_detail_returns_aggregate_fields(app_under_test):
    job_id = await _create_and_run_job(app_under_test)
    r = await app_under_test.get(f"/api/v1/jobs/{job_id}")
    assert r.status_code == 200, r.text
    body = r.json()

    # Legacy fields preserved.
    legacy_fields = {
        "id",
        "status",
        "brief",
        "target_duration_seconds",
        "watermark_required",
        "c2pa_required",
        "voice_mode",
        "script_text",
        "tts_backend",
        "audio_ref",
        "face_mode",
        "image_ref",
        "rejection_reason",
        "created_at",
        "updated_at",
    }
    assert legacy_fields.issubset(set(body.keys()))

    # Phase 4F-2 additions.
    aggregate_fields = {
        "current_stage",
        "progress_percent",
        "artifact_count",
        "compliance_event_count",
        "latest_qc_result",
        "final_export_summary",
    }
    assert aggregate_fields.issubset(set(body.keys()))

    # Pinned values for a fully-run job.
    assert body["progress_percent"] == 100.0
    assert body["artifact_count"] >= 1
    assert body["compliance_event_count"] >= 1
    assert isinstance(body["latest_qc_result"], dict)
    assert body["latest_qc_result"]["passed"] is True
    assert isinstance(body["final_export_summary"], dict)
    assert body["final_export_summary"]["passed_qc"] is True


async def test_job_detail_aggregate_fields_for_pending_job(app_under_test):
    job_id = await _create_pending_job(app_under_test)
    r = await app_under_test.get(f"/api/v1/jobs/{job_id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["progress_percent"] == 0.0
    assert body["artifact_count"] == 0
    assert body["latest_qc_result"] is None
    assert body["final_export_summary"] is None


# ---------------------------------------------------------------------------
# 4. JobProgress flat stage-name lists
# ---------------------------------------------------------------------------


async def test_progress_includes_pending_count_and_flat_stage_lists(app_under_test):
    job_id = await _create_pending_job(app_under_test)
    r = await app_under_test.get(f"/api/v1/jobs/{job_id}/progress")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pending_stages"] == 11
    assert body["completed_stages"] == 0
    assert body["failed_stages"] == 0
    assert isinstance(body["pending_stage_names"], list)
    assert len(body["pending_stage_names"]) == 11
    assert body["pending_stage_names"][0] == "policy_gate"
    assert body["pending_stage_names"][-1] == "publisher"
    assert body["completed_stage_names"] == []
    assert body["failed_stage_names"] == []


async def test_progress_flat_lists_for_published_job(app_under_test):
    job_id = await _create_and_run_job(app_under_test)
    r = await app_under_test.get(f"/api/v1/jobs/{job_id}/progress")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pending_stages"] == 0
    assert body["completed_stages"] == 11
    assert len(body["completed_stage_names"]) == 11
    assert body["completed_stage_names"][0] == "policy_gate"
    assert body["pending_stage_names"] == []
    assert body["failed_stage_names"] == []


# ---------------------------------------------------------------------------
# 5. ?status=… filter on the list endpoint
# ---------------------------------------------------------------------------


async def test_jobs_list_status_filter_returns_only_matching(app_under_test):
    await _create_pending_job(app_under_test)
    await _create_and_run_job(app_under_test)

    r_all = await app_under_test.get("/api/v1/jobs")
    assert r_all.status_code == 200
    assert len(r_all.json()) >= 2

    r_pending = await app_under_test.get("/api/v1/jobs?status=pending_compliance")
    assert r_pending.status_code == 200, r_pending.text
    payload = r_pending.json()
    assert len(payload) >= 1
    assert all(j["status"] == "pending_compliance" for j in payload)

    r_published = await app_under_test.get("/api/v1/jobs?status=published")
    assert r_published.status_code == 200, r_published.text
    assert all(j["status"] == "published" for j in r_published.json())


async def test_jobs_list_status_filter_invalid_value_returns_422(app_under_test):
    r = await app_under_test.get("/api/v1/jobs?status=not_a_real_status")
    assert r.status_code == 422


async def test_jobs_list_status_filter_combines_with_pagination(app_under_test):
    # Three pending jobs.
    for _ in range(3):
        await _create_pending_job(app_under_test)

    r = await app_under_test.get(
        "/api/v1/jobs?status=pending_compliance&limit=2&offset=0"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) == 2
    assert all(j["status"] == "pending_compliance" for j in body)


# ---------------------------------------------------------------------------
# Cross-cutting invariants
# ---------------------------------------------------------------------------


async def test_no_phase4f2_endpoint_returns_binary_content(app_under_test):
    job_id = await _create_and_run_job(app_under_test)
    # Hit every Phase 4F-2 surface and round-trip through json.dumps.
    paths = [
        "/api/v1/jobs",
        "/api/v1/jobs?status=published",
        f"/api/v1/jobs/{job_id}",
        f"/api/v1/jobs/{job_id}/progress",
        f"/api/v1/jobs/{job_id}/summary",
    ]
    for path in paths:
        r = await app_under_test.get(path)
        assert r.status_code == 200, (path, r.text)
        json.dumps(r.json())


async def test_phase4f2_responses_do_not_leak_signing_secrets(app_under_test):
    # The test signing key is set on the runner; make sure it never appears
    # in any of the new aggregate payloads (defensive — compliance events
    # may carry token metadata).
    job_id = await _create_and_run_job(app_under_test)
    paths = [
        "/api/v1/jobs",
        f"/api/v1/jobs/{job_id}",
        f"/api/v1/jobs/{job_id}/summary",
        f"/api/v1/jobs/{job_id}/progress",
    ]
    for path in paths:
        r = await app_under_test.get(path)
        assert r.status_code == 200, (path, r.text)
        assert "phase4f2-test-key-not-for-prod" not in r.text


async def test_phase4f2_alias_routes_resolve_under_api_v1(app_under_test):
    """Both /jobs/{id} and /api/v1/jobs/{id} should serve the new shapes."""
    job_id = await _create_and_run_job(app_under_test)
    for prefix in ("/jobs", "/api/v1/jobs"):
        # JobDetail aggregate.
        r = await app_under_test.get(f"{prefix}/{job_id}")
        assert r.status_code == 200, (prefix, r.text)
        body = r.json()
        assert body["progress_percent"] == 100.0
        assert "current_stage" in body
        # Summary.
        r2 = await app_under_test.get(f"{prefix}/{job_id}/summary")
        assert r2.status_code == 200, (prefix, r2.text)
        assert r2.json()["job"]["id"] == str(job_id)
