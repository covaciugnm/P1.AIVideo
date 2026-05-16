"""Phase 4A integration tests — job view API endpoints.

Verifies the eight endpoints the future web UI consumes:

- ``GET /jobs``                          — list of summaries.
- ``GET /jobs/{id}``                     — single job (Phase 1 contract preserved).
- ``GET /jobs/{id}/progress``            — aggregate progress + per-stage status.
- ``GET /jobs/{id}/timeline``            — stage_runs in canonical order.
- ``GET /jobs/{id}/artifacts``           — metadata-only artifact list.
- ``GET /jobs/{id}/compliance-events``   — compliance audit rows.
- ``GET /jobs/{id}/qc-report``           — structured QC report.
- ``GET /jobs/{id}/final-export``        — structured FinalExport manifest.

Plus:

- 404 on unknown job id (every endpoint).
- 404 on QC / final-export endpoints when the corresponding artifact
  doesn't exist for the job.
- No binary content leaks: every response body JSON-serializes and
  every value is a JSON-native type (no ``bytes``).
"""
from __future__ import annotations

import json
import uuid

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
        yield client, fake, tmp_path

    await fake.aclose()
    queue_publisher.reset_redis_client()
    await core_db.async_reset_engine()


def _runner_config():
    from agents.orchestrator.dag import DagRunnerConfig

    return DagRunnerConfig(
        signing_key="phase4a-test-key-not-for-prod",
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


async def _create_and_run_job(client, payload: dict | None = None) -> uuid.UUID:
    from agents.orchestrator.dag import DagRunner
    from app.core.db import get_sessionmaker

    r = await client.post("/jobs", json=payload or _valid_payload())
    assert r.status_code == 201, r.text
    job_id = uuid.UUID(r.json()["id"])
    await DagRunner(get_sessionmaker(), _runner_config()).run(job_id)
    return job_id


# ---------------------------------------------------------------------------
# Canonical stage list — pinned in common
# ---------------------------------------------------------------------------


def test_canonical_stage_list_matches_pipeline_yaml():
    """Phase 4A's progress endpoint reads CANONICAL_DAG_STAGES; tests pin
    that list to the actual pipeline YAML so the UI never disagrees
    with the DAG runner about stage order."""
    from agents.orchestrator.dag import load_stage_order
    from common.enums import CANONICAL_DAG_STAGES

    assert list(CANONICAL_DAG_STAGES) == load_stage_order()
    assert CANONICAL_DAG_STAGES[0] == "policy_gate"
    assert CANONICAL_DAG_STAGES[-1] == "publisher"
    assert len(CANONICAL_DAG_STAGES) == 11


# ---------------------------------------------------------------------------
# GET /jobs — list
# ---------------------------------------------------------------------------


async def test_list_jobs_returns_metadata_summaries(app_under_test):
    client, _, _ = app_under_test
    # Two jobs in increasing creation order; list should return them in
    # descending created_at order.
    id1 = await _create_and_run_job(client, _valid_payload("brief one"))
    id2 = await _create_and_run_job(client, _valid_payload("brief two"))

    r = await client.get("/jobs")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 2
    ids_seen = {item["id"] for item in body}
    assert {str(id1), str(id2)}.issubset(ids_seen)
    # Each summary has the expected fields.
    for item in body:
        assert {
            "id",
            "status",
            "brief",
            "target_duration_seconds",
            "voice_mode",
            "face_mode",
            "created_at",
            "updated_at",
            "current_stage",
            "progress_percent",
            "artifact_count",
        }.issubset(item.keys())
        assert item["status"] == "published"
        assert item["progress_percent"] == pytest.approx(100.0)
        # Phase 3D–3J produced 5 promoted artifacts per job
        # (audio + image only when provided; here just script/edit_plan/
        #  qc_report metadata/final_export). Audio + image refs not
        # provided in this payload → 4 artifacts.
        assert item["artifact_count"] >= 4


async def test_list_jobs_pagination(app_under_test):
    client, _, _ = app_under_test
    for i in range(3):
        await _create_and_run_job(client, _valid_payload(f"brief {i}"))

    r = await client.get("/jobs?limit=2&offset=0")
    assert r.status_code == 200
    assert len(r.json()) == 2
    r = await client.get("/jobs?limit=2&offset=2")
    assert r.status_code == 200
    assert len(r.json()) == 1


# ---------------------------------------------------------------------------
# GET /jobs/{id}  — detail
# ---------------------------------------------------------------------------


async def test_get_job_detail_returns_expected_fields(app_under_test):
    client, _, _ = app_under_test
    job_id = await _create_and_run_job(client)
    r = await client.get(f"/jobs/{job_id}")
    assert r.status_code == 200
    body = r.json()
    for key in (
        "id",
        "status",
        "brief",
        "target_duration_seconds",
        "watermark_required",
        "c2pa_required",
        "voice_mode",
        "tts_backend",
        "created_at",
        "updated_at",
    ):
        assert key in body
    assert body["status"] == "published"


async def test_get_job_returns_404_for_unknown_id(app_under_test):
    client, _, _ = app_under_test
    r = await client.get(f"/jobs/{uuid.uuid4()}")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /jobs/{id}/progress
# ---------------------------------------------------------------------------


async def test_progress_returns_100_when_published(app_under_test):
    client, _, _ = app_under_test
    job_id = await _create_and_run_job(client)
    r = await client.get(f"/jobs/{job_id}/progress")
    assert r.status_code == 200
    body = r.json()
    assert body["job_id"] == str(job_id)
    assert body["status"] == "published"
    assert body["total_stages"] == 11
    assert body["completed_stages"] == 11
    assert body["failed_stages"] == 0
    assert body["progress_percent"] == pytest.approx(100.0)
    assert body["current_stage"] is None
    # All eleven stage entries present, in canonical order, all succeeded.
    from common.enums import CANONICAL_DAG_STAGES

    assert [s["stage_name"] for s in body["stages"]] == list(CANONICAL_DAG_STAGES)
    assert all(s["status"] == "succeeded" for s in body["stages"])


async def test_progress_partial_for_pending_job(app_under_test):
    """A job that's been POSTed but not yet run shows 0% progress."""
    client, _, _ = app_under_test
    r = await client.post("/jobs", json=_valid_payload())
    job_id = uuid.UUID(r.json()["id"])

    r = await client.get(f"/jobs/{job_id}/progress")
    assert r.status_code == 200
    body = r.json()
    assert body["completed_stages"] == 0
    assert body["progress_percent"] == pytest.approx(0.0)
    assert body["current_stage"] == "policy_gate"
    assert all(s["status"] == "pending" for s in body["stages"])


async def test_progress_returns_404_for_unknown_job(app_under_test):
    client, _, _ = app_under_test
    r = await client.get(f"/jobs/{uuid.uuid4()}/progress")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /jobs/{id}/timeline
# ---------------------------------------------------------------------------


async def test_timeline_returns_stage_runs_in_canonical_order(app_under_test):
    client, _, _ = app_under_test
    job_id = await _create_and_run_job(client)
    r = await client.get(f"/jobs/{job_id}/timeline")
    assert r.status_code == 200
    body = r.json()
    from common.enums import CANONICAL_DAG_STAGES

    assert [e["stage_name"] for e in body] == list(CANONICAL_DAG_STAGES)
    for entry in body:
        for key in (
            "stage_name",
            "status",
            "started_at",
            "completed_at",
            "duration_ms",
            "error_message",
            "artifact_refs",
            "metadata_summary",
        ):
            assert key in entry
        # All stages succeeded for a clean run.
        assert entry["status"] == "succeeded"
        assert entry["duration_ms"] is not None
        assert entry["duration_ms"] >= 0
        # artifact_refs is a list of artifact NAMES (strings), not binary blobs.
        assert isinstance(entry["artifact_refs"], list)
        assert all(isinstance(a, str) for a in entry["artifact_refs"])


async def test_timeline_returns_404_for_unknown_job(app_under_test):
    client, _, _ = app_under_test
    r = await client.get(f"/jobs/{uuid.uuid4()}/timeline")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /jobs/{id}/artifacts
# ---------------------------------------------------------------------------


async def test_artifacts_returns_metadata_only_list(app_under_test):
    client, _, _ = app_under_test
    job_id = await _create_and_run_job(client)
    r = await client.get(f"/jobs/{job_id}/artifacts")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    # At minimum: script, edit_plan, qc_report (metadata), final_export.
    types = sorted(a["artifact_type"] for a in body)
    assert "script" in types
    assert "edit_plan" in types
    assert "metadata" in types  # qc_report
    assert "final_export" in types

    for art in body:
        for key in (
            "artifact_id",
            "artifact_type",
            "uri",
            "mime_type",
            "checksum_sha256",
            "size_bytes",
            "created_at",
            "stage_run_id",
            "metadata_summary",
        ):
            assert key in art
        # Every artifact URI must be a string scheme; no inline binary.
        assert isinstance(art["uri"], str)
        # Every field must be JSON-native (no bytes).
        assert isinstance(json.dumps(art), str)


async def test_artifacts_returns_404_for_unknown_job(app_under_test):
    client, _, _ = app_under_test
    r = await client.get(f"/jobs/{uuid.uuid4()}/artifacts")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /jobs/{id}/compliance-events
# ---------------------------------------------------------------------------


async def test_compliance_events_returns_records_in_order(app_under_test):
    client, _, _ = app_under_test
    job_id = await _create_and_run_job(client)
    r = await client.get(f"/jobs/{job_id}/compliance-events")
    assert r.status_code == 200
    body = r.json()
    # Phase 2 records four compliance gates: policy_gate, identity_guard,
    # pre_lipsync_auth, export_disclosure_validation.
    assert [e["event_type"] for e in body] == [
        "policy_gate",
        "identity_guard",
        "pre_lipsync_auth",
        "export_disclosure_validation",
    ]
    for event in body:
        for key in (
            "event_type",
            "decision",
            "reasons",
            "created_at",
            "metadata_summary",
        ):
            assert key in event
        assert event["decision"] == "accept"
    # The policy_gate row records the voice + face source under metadata.
    pg = body[0]
    assert "voice_source" in pg["metadata_summary"]
    assert "face_source" in pg["metadata_summary"]


# ---------------------------------------------------------------------------
# GET /jobs/{id}/qc-report
# ---------------------------------------------------------------------------


async def test_qc_report_endpoint_returns_structured_report(app_under_test):
    client, _, _ = app_under_test
    job_id = await _create_and_run_job(client)
    r = await client.get(f"/jobs/{job_id}/qc-report")
    assert r.status_code == 200
    body = r.json()
    for key in ("job_id", "artifact_id", "artifact_uri", "checksum_sha256",
                "qc_report", "created_at"):
        assert key in body
    assert body["job_id"] == str(job_id)
    report = body["qc_report"]
    assert report["passed"] is True
    assert [c["name"] for c in report["checks"]] == [
        "script_artifact_present",
        "segments_present",
        "total_duration_matches_target",
        "reel_draft_is_stub",
    ]


async def test_qc_report_404_when_qc_stage_never_ran(app_under_test):
    """A job that's been POSTed but not yet DAG-run has no qc stage."""
    client, _, _ = app_under_test
    r = await client.post("/jobs", json=_valid_payload())
    job_id = uuid.UUID(r.json()["id"])
    r = await client.get(f"/jobs/{job_id}/qc-report")
    assert r.status_code == 404


async def test_qc_report_404_for_unknown_job(app_under_test):
    client, _, _ = app_under_test
    r = await client.get(f"/jobs/{uuid.uuid4()}/qc-report")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /jobs/{id}/final-export
# ---------------------------------------------------------------------------


async def test_final_export_endpoint_returns_manifest(app_under_test):
    client, _, _ = app_under_test
    job_id = await _create_and_run_job(client)
    r = await client.get(f"/jobs/{job_id}/final-export")
    assert r.status_code == 200
    body = r.json()
    for key in ("job_id", "artifact_id", "artifact_uri", "checksum_sha256",
                "final_export", "created_at"):
        assert key in body
    manifest = body["final_export"]
    assert manifest["passed_qc"] is True
    assert manifest["status"] == "published"
    assert manifest["job_id"] == str(job_id)
    # Phase 9D: the publisher emits a ``placeholder://`` export URI when
    # the upstream reel_draft is itself metadata-only — no fake
    # ``reel_final.mp4`` claim. The manifest still declares the intended
    # mime type even when the bytes aren't there yet.
    assert manifest["export_uri"].startswith("placeholder://")
    assert not manifest["export_uri"].endswith(".mp4")
    assert manifest["mime_type"] == "video/mp4"


async def test_final_export_404_when_publisher_never_ran(app_under_test):
    client, _, _ = app_under_test
    r = await client.post("/jobs", json=_valid_payload())
    job_id = uuid.UUID(r.json()["id"])
    r = await client.get(f"/jobs/{job_id}/final-export")
    assert r.status_code == 404


async def test_final_export_404_for_unknown_job(app_under_test):
    client, _, _ = app_under_test
    r = await client.get(f"/jobs/{uuid.uuid4()}/final-export")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# No binary content leaks
# ---------------------------------------------------------------------------


async def test_no_endpoint_returns_binary_content(app_under_test):
    """Every Phase 4A response must round-trip cleanly through json.dumps —
    a proxy for "no bytes / binary payloads"."""
    client, _, _ = app_under_test
    job_id = await _create_and_run_job(client)
    endpoints = [
        "/jobs",
        f"/jobs/{job_id}",
        f"/jobs/{job_id}/progress",
        f"/jobs/{job_id}/timeline",
        f"/jobs/{job_id}/artifacts",
        f"/jobs/{job_id}/compliance-events",
        f"/jobs/{job_id}/qc-report",
        f"/jobs/{job_id}/final-export",
    ]
    for path in endpoints:
        r = await client.get(path)
        assert r.status_code == 200, f"{path} → {r.status_code}: {r.text}"
        # FastAPI returns JSON; r.json() succeeds = JSON-parseable = no binary.
        body = r.json()
        # And json.dumps must round-trip without TypeError.
        assert isinstance(json.dumps(body), str), path
