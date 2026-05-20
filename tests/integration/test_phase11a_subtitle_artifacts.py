"""Phase 11A — subtitle artifact contract."""
from __future__ import annotations

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


def _from_inputs_body(**overrides):
    body = {
        "brief": "Demo RO — subtitrări",
        "target_duration_seconds": 15,
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "watermark_required": True,
        "c2pa_required": True,
        "voice_mode": "tts",
        "script_text": (
            "Bună ziua! Acesta este primul rând. "
            "Acesta este al doilea rând? "
            "Iar acesta este al treilea rând."
        ),
        "subtitle_enabled": True,
        "subtitle_languages": ["ro"],
        "subtitle_format": "srt",
    }
    body.update(overrides)
    return body


async def test_subtitle_artifact_generated_on_from_inputs(app_client):
    r = await app_client.post(
        "/api/v1/jobs/from-inputs", json=_from_inputs_body()
    )
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]
    arts = await app_client.get(f"/api/v1/jobs/{job_id}/artifacts")
    types = sorted({a["artifact_type"] for a in arts.json()})
    assert "subtitle" in types, types
    sub = next(a for a in arts.json() if a["artifact_type"] == "subtitle")
    assert sub["mime_type"] == "application/x-subrip"
    assert sub["metadata_summary"]["language_code"] == "ro"
    assert sub["metadata_summary"]["format"] == "srt"
    assert sub["metadata_summary"]["real_timing"] is False
    assert sub["metadata_summary"]["alignment"] == "approximate"


async def test_subtitle_vtt_format_persists(app_client):
    r = await app_client.post(
        "/api/v1/jobs/from-inputs",
        json=_from_inputs_body(subtitle_format="vtt"),
    )
    assert r.status_code == 201
    arts = await app_client.get(f"/api/v1/jobs/{r.json()['id']}/artifacts")
    sub = next(a for a in arts.json() if a["artifact_type"] == "subtitle")
    assert sub["mime_type"] == "text/vtt"
    assert sub["metadata_summary"]["format"] == "vtt"


async def test_subtitle_content_endpoint_serves_bytes(app_client):
    r = await app_client.post(
        "/api/v1/jobs/from-inputs", json=_from_inputs_body()
    )
    arts = await app_client.get(f"/api/v1/jobs/{r.json()['id']}/artifacts")
    sub = next(a for a in arts.json() if a["artifact_type"] == "subtitle")
    content = await app_client.get(
        f"/api/v1/artifacts/{sub['artifact_id']}/content"
    )
    assert content.status_code == 200
    body = content.text
    # SRT starts with "1\n" (cue index).
    assert body.startswith("1\n") or body.startswith("1\r")


async def test_subtitle_two_languages(app_client):
    r = await app_client.post(
        "/api/v1/jobs/from-inputs",
        json=_from_inputs_body(subtitle_languages=["ro", "en"]),
    )
    assert r.status_code == 201
    arts = await app_client.get(f"/api/v1/jobs/{r.json()['id']}/artifacts")
    subs = [a for a in arts.json() if a["artifact_type"] == "subtitle"]
    langs = sorted(a["metadata_summary"]["language_code"] for a in subs)
    assert langs == ["en", "ro"]


async def test_burn_in_flag_records_not_implemented(app_client):
    r = await app_client.post(
        "/api/v1/jobs/from-inputs",
        json=_from_inputs_body(subtitle_burn_in=True),
    )
    assert r.status_code == 201
    arts = await app_client.get(f"/api/v1/jobs/{r.json()['id']}/artifacts")
    sub = next(a for a in arts.json() if a["artifact_type"] == "subtitle")
    # Phase 21 — burn-in is now wired through the orchestrator into the
    # editor stage (ffmpeg subtitles= filter). The sidecar row records
    # the operator's INTENT; the actual bake happens when the DAG runs.
    assert sub["metadata_summary"]["burn_in_status"] == "queued_for_editor"


async def test_no_subtitle_when_disabled(app_client):
    r = await app_client.post(
        "/api/v1/jobs/from-inputs",
        json=_from_inputs_body(subtitle_enabled=False),
    )
    arts = await app_client.get(f"/api/v1/jobs/{r.json()['id']}/artifacts")
    types = {a["artifact_type"] for a in arts.json()}
    assert "subtitle" not in types
