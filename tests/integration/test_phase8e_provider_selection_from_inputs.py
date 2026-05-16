"""Phase 8E Part A — /api/v1/jobs/from-inputs accepts provider_selection.

Reproduces the browser bug ("extra_forbidden on body.provider_selection")
and pins the fix:

- ``JobFromInputsRequest`` accepts ``provider_selection``.
- All five Phase 6D fields round-trip
  (script_provider_id / tts_provider_id / video_provider_id /
  audio_processor_id / image_processor_id) plus the legacy
  ``script_model`` / ``tts_model`` / ``video_model``.
- Unknown future provider ids are accepted at write time (the runtime
  is the gate — see Phase 6D ``test_job_provider_selection_accepts_future_unknown_ids``).
- Unknown extra keys inside ``provider_selection`` still return 422.
"""
from __future__ import annotations

import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient


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


_FULL_PROVIDER_SELECTION = {
    "script_provider_id": "template",
    "script_model": "qwen3.6",
    "tts_provider_id": "piper",
    "tts_model": "en_US-amy-medium",
    "video_provider_id": "sadtalker",
    "video_model": "sadtalker-v1",
    "audio_processor_id": "ffmpeg_convert",
    "image_processor_id": "stdlib_image_validation",
}


_BASE_PAYLOAD = {
    "brief": "phase 8e from-inputs provider_selection",
    "target_duration_seconds": 30,
    "synthetic_person_confirmed": True,
    "consent_confirmed": True,
    "watermark_required": True,
    "c2pa_required": True,
    "voice_mode": "tts",
    "script_text": "phase 8e",
}


async def test_from_inputs_accepts_full_provider_selection(app_under_test):
    """Previously: 422 ``extra_forbidden``. Phase 8E fix: 201 + the
    provider_selection round-trips on the response."""
    r = await app_under_test.post(
        "/api/v1/jobs/from-inputs",
        json={**_BASE_PAYLOAD, "provider_selection": _FULL_PROVIDER_SELECTION},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["provider_selection"] == _FULL_PROVIDER_SELECTION


async def test_from_inputs_accepts_partial_provider_selection(app_under_test):
    sel = {"script_provider_id": "template", "tts_provider_id": "piper"}
    r = await app_under_test.post(
        "/api/v1/jobs/from-inputs",
        json={**_BASE_PAYLOAD, "provider_selection": sel},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["provider_selection"]["script_provider_id"] == "template"
    assert body["provider_selection"]["tts_provider_id"] == "piper"


async def test_from_inputs_accepts_unknown_future_provider_ids(app_under_test):
    """Phase 6D contract: unknown ids accepted at write time. Runtime
    is the gate. Pin that ``/from-inputs`` follows the same contract."""
    sel = {
        "script_provider_id": "custom_future_llm",
        "tts_provider_id": "custom_future_tts",
        "video_provider_id": "custom_future_video",
    }
    r = await app_under_test.post(
        "/api/v1/jobs/from-inputs",
        json={**_BASE_PAYLOAD, "provider_selection": sel},
    )
    assert r.status_code == 201, r.text
    assert r.json()["provider_selection"]["video_provider_id"] == "custom_future_video"


async def test_from_inputs_rejects_unknown_field_inside_provider_selection(
    app_under_test,
):
    sel = {"definitely_not_a_field": "x"}
    r = await app_under_test.post(
        "/api/v1/jobs/from-inputs",
        json={**_BASE_PAYLOAD, "provider_selection": sel},
    )
    assert r.status_code == 422


async def test_from_inputs_omitting_provider_selection_still_works(
    app_under_test,
):
    """Backward compat: pre-8E clients didn't send the field."""
    r = await app_under_test.post(
        "/api/v1/jobs/from-inputs",
        json=_BASE_PAYLOAD,
    )
    assert r.status_code == 201, r.text
    assert r.json()["provider_selection"] is None


async def test_from_inputs_provider_selection_surfaces_in_get_job(
    app_under_test,
):
    r = await app_under_test.post(
        "/api/v1/jobs/from-inputs",
        json={**_BASE_PAYLOAD, "provider_selection": _FULL_PROVIDER_SELECTION},
    )
    job_id = r.json()["id"]
    detail = await app_under_test.get(f"/api/v1/jobs/{job_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["provider_selection"] == _FULL_PROVIDER_SELECTION
