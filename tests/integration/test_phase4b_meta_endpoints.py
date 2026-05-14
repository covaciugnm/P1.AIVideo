"""Phase 4B integration tests — system + config metadata endpoints.

Endpoints under test:

- ``GET /api/v1/stages``
- ``GET /api/v1/artifact-types``
- ``GET /api/v1/config/ui-options``
- ``GET /api/v1/system/status``

Plus the new ``/api/v1/jobs`` alias — the existing Phase 4A endpoints
must resolve under both the legacy ``/jobs`` prefix and the new
``/api/v1/jobs`` prefix so the frontend can speak a single ``/api/v1/*``
prefix everywhere.

Boundary expectations (Phase 4B):

- Read-only.
- No binary content in responses.
- No model weights loaded; no external calls.
"""
from __future__ import annotations

import uuid

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
        yield client

    await fake.aclose()
    queue_publisher.reset_redis_client()
    await core_db.async_reset_engine()


# ---------------------------------------------------------------------------
# GET /api/v1/stages
# ---------------------------------------------------------------------------


async def test_stages_endpoint_returns_canonical_dag_order(app_under_test):
    from common.enums import CANONICAL_DAG_STAGES

    r = await app_under_test.get("/api/v1/stages")
    assert r.status_code == 200, r.text
    payload = r.json()
    assert isinstance(payload, list)
    assert [s["name"] for s in payload] == list(CANONICAL_DAG_STAGES)
    assert [s["order"] for s in payload] == list(range(len(CANONICAL_DAG_STAGES)))
    # Labels are non-empty human strings (no underscores).
    for entry in payload:
        assert entry["label"]
        assert "_" not in entry["label"]


# ---------------------------------------------------------------------------
# GET /api/v1/artifact-types
# ---------------------------------------------------------------------------


async def test_artifact_types_endpoint_lists_enum_values(app_under_test):
    from common.enums import ArtifactType

    r = await app_under_test.get("/api/v1/artifact-types")
    assert r.status_code == 200, r.text
    payload = r.json()
    values = [e["value"] for e in payload]
    expected = [at.value for at in ArtifactType]
    assert sorted(values) == sorted(expected)
    # No extras, no missing.
    assert len(values) == len(expected)


# ---------------------------------------------------------------------------
# GET /api/v1/config/ui-options
# ---------------------------------------------------------------------------


async def test_ui_options_contains_voice_face_and_duration_bounds(app_under_test):
    r = await app_under_test.get("/api/v1/config/ui-options")
    assert r.status_code == 200, r.text
    payload = r.json()

    # voice_modes
    voice_values = {v["value"] for v in payload["voice_modes"]}
    assert voice_values == {"tts", "provided_audio"}
    tts_entry = next(v for v in payload["voice_modes"] if v["value"] == "tts")
    assert tts_entry["requires_script_text"] is True
    assert tts_entry["requires_audio_artifact"] is False
    pa_entry = next(v for v in payload["voice_modes"] if v["value"] == "provided_audio")
    assert pa_entry["requires_script_text"] is False
    assert pa_entry["requires_audio_artifact"] is True

    # face_modes
    assert [f["value"] for f in payload["face_modes"]] == ["provided_image"]
    assert payload["face_modes"][0]["requires_image_artifact"] is True

    # tts_backends — Phase 4B exposes piper only.
    assert payload["tts_backends"] == ["piper"]

    # duration bounds
    db = payload["duration_bounds"]
    assert db["min_seconds"] < db["default_seconds"] <= db["max_seconds"]

    # upload limits
    ul = payload["upload_limits"]
    assert ul["audio_max_bytes"] > 0
    assert ul["image_max_bytes"] > 0
    assert ul["script_text_max_chars"] > 0
    assert "audio/wav" in ul["accepted_audio_mime_types"]
    assert "image/png" in ul["accepted_image_mime_types"]
    assert ".wav" in ul["accepted_audio_extensions"]
    assert {".png", ".jpg", ".jpeg", ".webp"} <= set(ul["accepted_image_extensions"])

    # enum lists for the UI
    assert "pending_compliance" in payload["job_statuses"]
    assert "running" in payload["stage_statuses"]
    assert "ok" in payload["provider_health_statuses"]
    assert isinstance(payload["artifact_types"], list)
    assert all(set(e.keys()) == {"value", "label"} for e in payload["artifact_types"])


# ---------------------------------------------------------------------------
# GET /api/v1/system/status
# ---------------------------------------------------------------------------


async def test_system_status_is_healthy_in_test_env(app_under_test):
    r = await app_under_test.get("/api/v1/system/status")
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["app_name"]
    assert payload["app_version"]
    assert payload["phase"] == "4B"
    assert payload["database_reachable"] is True
    assert payload["database_error"] is None
    assert "server_time" in payload


# ---------------------------------------------------------------------------
# /api/v1/jobs alias
# ---------------------------------------------------------------------------


def _valid_payload() -> dict:
    return {
        "brief": "Three calming bedtime habits.",
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "target_duration_seconds": 30,
        "watermark_required": True,
        "c2pa_required": True,
        "script_text": "Tip one: avoid screens.",
    }


async def test_api_v1_jobs_alias_create_and_list(app_under_test):
    # Create via /api/v1/jobs
    r = await app_under_test.post("/api/v1/jobs", json=_valid_payload())
    assert r.status_code == 201, r.text
    job_id = uuid.UUID(r.json()["id"])

    # The legacy /jobs/{id} resolves the same job.
    r1 = await app_under_test.get(f"/jobs/{job_id}")
    r2 = await app_under_test.get(f"/api/v1/jobs/{job_id}")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"] == str(job_id)

    # GET /api/v1/jobs returns the summary list including the new job.
    r3 = await app_under_test.get("/api/v1/jobs")
    assert r3.status_code == 200
    ids = [j["id"] for j in r3.json()]
    assert str(job_id) in ids


async def test_api_v1_jobs_alias_subroutes_resolve(app_under_test):
    r = await app_under_test.post("/api/v1/jobs", json=_valid_payload())
    assert r.status_code == 201, r.text
    job_id = uuid.UUID(r.json()["id"])

    for sub in ("progress", "timeline", "artifacts", "compliance-events"):
        legacy = await app_under_test.get(f"/jobs/{job_id}/{sub}")
        aliased = await app_under_test.get(f"/api/v1/jobs/{job_id}/{sub}")
        assert legacy.status_code == 200, (sub, legacy.text)
        assert aliased.status_code == 200, (sub, aliased.text)
        assert legacy.json() == aliased.json()


async def test_api_v1_jobs_alias_404s_for_unknown_id(app_under_test):
    missing = uuid.uuid4()
    r = await app_under_test.get(f"/api/v1/jobs/{missing}")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# No-binary leakage smoke test.
# ---------------------------------------------------------------------------


async def test_meta_endpoints_serialize_as_json(app_under_test):
    import json

    for path in (
        "/api/v1/stages",
        "/api/v1/artifact-types",
        "/api/v1/config/ui-options",
        "/api/v1/system/status",
    ):
        r = await app_under_test.get(path)
        assert r.status_code == 200, (path, r.text)
        # Round-trip through json.dumps to assert no bytes leaked.
        json.dumps(r.json())
