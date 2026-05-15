"""Phase 4F integration tests.

Covers:
- /api/v1/providers (LLM/TTS/video-generator metadata).
- /api/v1/tts/generate → 503 with code tts_provider_not_configured.
- /api/v1/artifacts/{id}/content safe serving + 404 / 403 / 415.
- Job create + update accept provider_selection round-trip.
- Audio upload now accepts MP3 etc.

Boundaries:
- No real TTS runtime configured.
- ffmpeg may or may not be on PATH — tests that need it skip cleanly.
"""
from __future__ import annotations

import io
import shutil
import uuid
import wave

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def app_under_test(monkeypatch, tmp_path):
    audio_root = tmp_path / "audio"
    image_root = tmp_path / "images"
    text_root = tmp_path / "text"
    monkeypatch.setenv("UPLOAD_AUDIO_ROOT", str(audio_root))
    monkeypatch.setenv("UPLOAD_IMAGE_ROOT", str(image_root))
    monkeypatch.setenv("UPLOAD_TEXT_ROOT", str(text_root))
    monkeypatch.setenv("PROVIDED_AUDIO_ALLOWED_ROOTS", str(audio_root))
    monkeypatch.setenv("PROVIDED_IMAGE_ALLOWED_ROOTS", str(image_root))
    monkeypatch.setenv("AUDIO_MAX_FILE_SIZE_BYTES", "1048576")
    monkeypatch.setenv("IMAGE_MAX_FILE_SIZE_BYTES", "524288")
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
        yield client, tmp_path, audio_root, image_root

    await fake.aclose()
    queue_publisher.reset_redis_client()
    await core_db.async_reset_engine()


def _make_wav_bytes(*, duration_sec: float = 0.3, sample_rate: int = 22050) -> bytes:
    n_frames = int(duration_sec * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b"\x00\x00" * n_frames)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# /api/v1/providers
# ---------------------------------------------------------------------------


async def test_providers_endpoint_returns_three_categories(app_under_test):
    client, *_ = app_under_test
    r = await client.get("/api/v1/providers")
    assert r.status_code == 200, r.text
    body = r.json()
    # Phase 6D added audio_processor + image_processor categories; the
    # original three keys remain present.
    assert {"llm", "tts", "video_generator"}.issubset(set(body.keys()))
    # Template LLM is always available.
    assert any(p["provider_id"] == "template" and p["status"] == "available"
               for p in body["llm"])
    # Piper is the canonical TTS — present but not configured in tests.
    assert any(p["provider_id"] == "piper" for p in body["tts"])
    # SadTalker placeholder visible.
    assert any(p["provider_id"] == "sadtalker"
               and p["status"] == "not_implemented"
               for p in body["video_generator"])


async def test_providers_per_category_endpoints(app_under_test):
    client, *_ = app_under_test
    for sub in ("llm", "tts", "video-generators"):
        r = await client.get(f"/api/v1/providers/{sub}")
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)
        assert len(r.json()) >= 1


async def test_providers_response_carries_no_secret_keys(app_under_test, monkeypatch):
    # Even when an API key env var is set, the providers endpoint must not
    # echo it back. The endpoint only exposes status / model / endpoint
    # description, not the key itself.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-x")
    client, *_ = app_under_test
    r = await client.get("/api/v1/providers")
    assert "sk-should-not-leak" not in r.text


# ---------------------------------------------------------------------------
# /api/v1/tts/generate
# ---------------------------------------------------------------------------


async def test_tts_generate_returns_503_when_piper_not_ready(app_under_test):
    """Phase 5A categorises the 503 by what's actually missing.

    With piper-tts not installed we get ``tts_runtime_missing``; with the
    runtime installed but no voice files we get ``tts_assets_missing``;
    with neither, ``tts_provider_not_configured``. Any of these is a
    valid "Piper not ready" signal — the test pins the union.
    """
    import importlib.util

    client, *_ = app_under_test
    r = await client.post(
        "/api/v1/tts/generate",
        json={"script_text": "Hello world.", "tts_provider_id": "piper"},
    )
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] in {
        "tts_runtime_missing",
        "tts_assets_missing",
        "tts_provider_not_configured",
    }
    assert detail["provider_id"] == "piper"
    if importlib.util.find_spec("piper") is None:
        assert detail["code"] == "tts_runtime_missing"


async def test_tts_generate_rejects_empty_script(app_under_test):
    client, *_ = app_under_test
    r = await client.post(
        "/api/v1/tts/generate",
        json={"script_text": "", "tts_provider_id": "piper"},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# /api/v1/artifacts/{id}/content
# ---------------------------------------------------------------------------


async def test_artifact_content_serves_uploaded_audio(app_under_test):
    client, *_ = app_under_test
    wav = _make_wav_bytes()
    files = {"file": ("clip.wav", wav, "audio/wav")}
    up = await client.post("/api/v1/uploads/audio", files=files)
    assert up.status_code == 201, up.text
    artifact_id = up.json()["artifact_id"]

    r = await client.get(f"/api/v1/artifacts/{artifact_id}/content")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/wav")
    # FastAPI's FileResponse handles range, but plain GET returns the body.
    assert r.content[:4] == b"RIFF"


async def test_artifact_content_404_on_unknown(app_under_test):
    client, *_ = app_under_test
    r = await client.get(f"/api/v1/artifacts/{uuid.uuid4()}/content")
    assert r.status_code == 404


async def test_artifact_content_rejects_non_serveable_type(app_under_test):
    """Register an artifact with a type outside the serve allow-list."""
    client, _, _, _ = app_under_test
    from app.core.db import get_sessionmaker
    from app.services import artifact_service

    sm = get_sessionmaker()
    async with sm() as session:
        art = await artifact_service.register_artifact(
            session,
            artifact_type="video",
            uri="file:///tmp/non-serveable.bin",
            local_path="/tmp/non-serveable.bin",
            mime_type="video/mp4",
        )
        await session.commit()
        artifact_id = art.id

    r = await client.get(f"/api/v1/artifacts/{artifact_id}/content")
    assert r.status_code == 415


async def test_artifact_content_rejects_path_outside_allowed_roots(app_under_test, tmp_path):
    client, root_tmp, _, _ = app_under_test
    # Register an artifact whose local_path points outside the configured
    # upload + provided-asset roots (e.g. another tmp dir).
    outside = tmp_path / "outside"
    outside.mkdir()
    bad = outside / "secret.wav"
    bad.write_bytes(_make_wav_bytes())

    from app.core.db import get_sessionmaker
    from app.services import artifact_service

    sm = get_sessionmaker()
    async with sm() as session:
        art = await artifact_service.register_artifact(
            session,
            artifact_type="audio",
            uri=bad.as_uri(),
            local_path=str(bad),
            mime_type="audio/wav",
        )
        await session.commit()
        artifact_id = art.id

    r = await client.get(f"/api/v1/artifacts/{artifact_id}/content")
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Audio upload broader formats
# ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
async def test_audio_upload_accepts_mp3_with_ffmpeg(app_under_test, tmp_path):
    """When ffmpeg is on PATH, MP3 uploads should transcode to PCM WAV.

    We generate a real (tiny) MP3 via ffmpeg so the decoder is happy.
    """
    import subprocess

    src_wav = tmp_path / "src.wav"
    src_wav.write_bytes(_make_wav_bytes(duration_sec=0.5))
    src_mp3 = tmp_path / "src.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src_wav), str(src_mp3)],
        check=True,
        timeout=15,
    )

    client, *_ = app_under_test
    files = {"file": ("clip.mp3", src_mp3.read_bytes(), "audio/mpeg")}
    r = await client.post("/api/v1/uploads/audio", files=files)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["mime_type"] == "audio/wav"
    md = body["metadata_summary"]
    assert md["converted_to_wav"] is True
    assert md["needs_conversion"] is False
    assert md["original_extension"] == ".mp3"


# ---------------------------------------------------------------------------
# Job provider_selection round-trip
# ---------------------------------------------------------------------------


def _valid_create_payload(provider_selection: dict | None = None) -> dict:
    return {
        "brief": "Three calming bedtime habits.",
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "target_duration_seconds": 30,
        "watermark_required": True,
        "c2pa_required": True,
        "script_text": "Tip one: avoid screens.",
        **({"provider_selection": provider_selection} if provider_selection else {}),
    }


async def test_create_job_accepts_provider_selection(app_under_test):
    client, *_ = app_under_test
    sel = {
        "script_provider_id": "template",
        "script_model": "static-v1",
        "tts_provider_id": "piper",
        "tts_model": "en_US-amy-medium",
        "video_provider_id": "sadtalker",
    }
    r = await client.post("/api/v1/jobs", json=_valid_create_payload(sel))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["provider_selection"] is not None
    assert body["provider_selection"]["script_provider_id"] == "template"
    assert body["provider_selection"]["tts_provider_id"] == "piper"
    assert body["provider_selection"]["video_provider_id"] == "sadtalker"


async def test_create_job_without_provider_selection_keeps_null(app_under_test):
    client, *_ = app_under_test
    r = await client.post("/api/v1/jobs", json=_valid_create_payload())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["provider_selection"] is None


async def test_patch_job_provider_selection(app_under_test):
    client, *_ = app_under_test
    r = await client.post("/api/v1/jobs", json=_valid_create_payload())
    assert r.status_code == 201
    job_id = r.json()["id"]

    patch = {"provider_selection": {"tts_provider_id": "piper"}}
    r2 = await client.patch(f"/api/v1/jobs/{job_id}", json=patch)
    assert r2.status_code == 200, r2.text
    assert r2.json()["provider_selection"]["tts_provider_id"] == "piper"


async def test_create_job_rejects_unknown_provider_field(app_under_test):
    client, *_ = app_under_test
    sel = {"unknown_field": "x"}
    r = await client.post("/api/v1/jobs", json=_valid_create_payload(sel))
    assert r.status_code == 422
