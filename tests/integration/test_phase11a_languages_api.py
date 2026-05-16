"""Phase 11A — language config + job language/subtitle persistence."""
from __future__ import annotations

import uuid

import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def app_client(monkeypatch, tmp_path):
    monkeypatch.setenv("UPLOAD_AUDIO_ROOT", str(tmp_path / "audio"))
    monkeypatch.setenv("UPLOAD_IMAGE_ROOT", str(tmp_path / "images"))
    monkeypatch.setenv("UPLOAD_TEXT_ROOT", str(tmp_path / "text"))
    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path / "artifacts"))

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


def _base_create_payload(**overrides):
    body = {
        "brief": "Demo RO — Limbă și subtitrări",
        "target_duration_seconds": 15,
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "watermark_required": True,
        "c2pa_required": True,
        "voice_mode": "tts",
        "script_text": "Acesta este un test de limbă.",
    }
    body.update(overrides)
    return body


# ---------- /config/languages ----------


async def test_languages_endpoint_returns_ro_and_en(app_client):
    r = await app_client.get("/api/v1/config/languages")
    assert r.status_code == 200
    data = r.json()
    codes = [row["code"] for row in data["available_languages"]]
    assert "ro" in codes and "en" in codes
    assert data["default_ui_language"] == "ro"
    assert data["default_video_language"] == "ro"
    assert data["subtitle_defaults"]["supported_formats"] == ["srt", "vtt"]
    assert data["subtitle_defaults"]["burn_in_supported"] is False


# ---------- /settings/ui ----------


async def test_ui_settings_get_default_is_ro(app_client):
    r = await app_client.get("/api/v1/settings/ui")
    assert r.status_code == 200
    body = r.json()
    assert body["ui_language"] == "ro"
    assert body["default_video_language"] == "ro"


async def test_ui_settings_patch_persists(app_client):
    r = await app_client.patch(
        "/api/v1/settings/ui", json={"ui_language": "en"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["ui_language"] == "en"
    # Round-trip GET sees the change.
    r2 = await app_client.get("/api/v1/settings/ui")
    assert r2.json()["ui_language"] == "en"


async def test_ui_settings_patch_invalid_language_rejected(app_client):
    r = await app_client.patch("/api/v1/settings/ui", json={"ui_language": "fr"})
    assert r.status_code == 422, r.text


# ---------- jobs: language + subtitle persistence ----------


async def test_job_create_defaults_video_language_ro(app_client):
    body = _base_create_payload()
    r = await app_client.post("/api/v1/jobs", json=body)
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["video_language"] == "ro"
    assert job["subtitle_enabled"] is False
    assert job["subtitle_format"] == "srt"


async def test_job_create_accepts_video_language_en(app_client):
    body = _base_create_payload(video_language="en")
    r = await app_client.post("/api/v1/jobs", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["video_language"] == "en"


async def test_job_create_invalid_video_language_422(app_client):
    body = _base_create_payload(video_language="zz")
    r = await app_client.post("/api/v1/jobs", json=body)
    assert r.status_code == 422, r.text


async def test_subtitle_enabled_defaults_to_video_language(app_client):
    body = _base_create_payload(video_language="ro", subtitle_enabled=True)
    r = await app_client.post("/api/v1/jobs", json=body)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["subtitle_enabled"] is True
    # When no explicit list is sent we default to [video_language].
    assert out["subtitle_languages"] == ["ro"]


async def test_subtitle_languages_explicit_persist(app_client):
    body = _base_create_payload(
        video_language="ro",
        subtitle_enabled=True,
        subtitle_languages=["ro", "en"],
        subtitle_format="vtt",
        subtitle_burn_in=True,
    )
    r = await app_client.post("/api/v1/jobs", json=body)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["subtitle_languages"] == ["ro", "en"]
    assert out["subtitle_format"] == "vtt"
    assert out["subtitle_burn_in"] is True


async def test_subtitle_format_must_be_srt_or_vtt(app_client):
    body = _base_create_payload(subtitle_format="ass")
    r = await app_client.post("/api/v1/jobs", json=body)
    assert r.status_code == 422


async def test_subtitle_language_must_be_supported(app_client):
    body = _base_create_payload(
        subtitle_enabled=True, subtitle_languages=["xx"]
    )
    r = await app_client.post("/api/v1/jobs", json=body)
    assert r.status_code == 422


# ---------- patch ----------


async def test_patch_updates_language_fields(app_client):
    create = await app_client.post(
        "/api/v1/jobs", json=_base_create_payload(video_language="ro")
    )
    jid = create.json()["id"]
    r = await app_client.patch(
        f"/api/v1/jobs/{jid}", json={"video_language": "en"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["video_language"] == "en"


# ---------- list / summary surface ----------


async def test_list_summary_contains_language_fields(app_client):
    await app_client.post(
        "/api/v1/jobs",
        json=_base_create_payload(
            video_language="en", subtitle_enabled=True, subtitle_languages=["en"]
        ),
    )
    r = await app_client.get("/api/v1/jobs")
    rows = r.json()
    assert rows, "expected at least one job"
    last = rows[0]
    assert "video_language" in last
    assert "subtitle_enabled" in last


# ---------- from-inputs path ----------


async def test_from_inputs_accepts_language_fields(app_client):
    body = {
        "brief": "Demo RO — from-inputs language",
        "target_duration_seconds": 15,
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "watermark_required": True,
        "c2pa_required": True,
        "voice_mode": "tts",
        "script_text": "Text de test.",
        "video_language": "en",
        "subtitle_enabled": True,
        "subtitle_languages": ["en"],
        "subtitle_format": "vtt",
    }
    r = await app_client.post("/api/v1/jobs/from-inputs", json=body)
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["video_language"] == "en"
    assert job["subtitle_languages"] == ["en"]
    assert job["subtitle_format"] == "vtt"


async def test_from_inputs_rejects_invalid_language(app_client):
    body = {
        "brief": "Demo RO — invalid language",
        "target_duration_seconds": 15,
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "watermark_required": True,
        "c2pa_required": True,
        "voice_mode": "tts",
        "script_text": "Test.",
        "video_language": "zz",
    }
    r = await app_client.post("/api/v1/jobs/from-inputs", json=body)
    assert r.status_code == 422
