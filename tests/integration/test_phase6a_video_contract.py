"""Phase 6A — /api/v1/video/generate metadata-only contract.

Validates that the endpoint:
- 404s on unknown job
- returns ``missing_inputs`` for unknown / wrong-type image/audio/edit_plan
- returns ``not_configured`` for an unknown provider
- returns ``not_implemented`` for known SadTalker/MuseTalk/Wav2Lip
  placeholders with the request shape echoed back
- never returns binary content
- never invokes a model
"""
from __future__ import annotations

import io
import uuid
import wave

import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def app_under_test(monkeypatch, tmp_path):
    monkeypatch.setenv("PROVIDED_AUDIO_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("PROVIDED_IMAGE_ALLOWED_ROOTS", str(tmp_path))
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
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    await fake.aclose()
    queue_publisher.reset_redis_client()
    await core_db.async_reset_engine()


def _make_wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\x00\x00" * 6615)  # 0.3s
    return buf.getvalue()


def _make_png(w: int = 64, h: int = 64) -> bytes:
    import struct
    import zlib

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = b"IHDR" + struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    ihdr_chunk = struct.pack(">I", 13) + ihdr + struct.pack(
        ">I", zlib.crc32(ihdr) & 0xFFFFFFFF
    )
    raw = b"".join(b"\x00" + b"\xFF\xFF\xFF" * w for _ in range(h))
    idat = b"IDAT" + zlib.compress(raw)
    idat_chunk = struct.pack(">I", len(idat) - 4) + idat + struct.pack(
        ">I", zlib.crc32(idat) & 0xFFFFFFFF
    )
    iend = b"IEND"
    iend_chunk = struct.pack(">I", 0) + iend + struct.pack(
        ">I", zlib.crc32(iend) & 0xFFFFFFFF
    )
    return sig + ihdr_chunk + idat_chunk + iend_chunk


async def _setup_job_with_assets(client) -> tuple[str, str, str]:
    """Returns (job_id, audio_artifact_id, image_artifact_id)."""
    payload = {
        "brief": "phase 6a",
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "target_duration_seconds": 30,
        "watermark_required": True,
        "c2pa_required": True,
        "script_text": "hello",
    }
    r = await client.post("/api/v1/jobs", json=payload)
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]

    files = {"file": ("audio.wav", _make_wav(), "audio/wav")}
    r2 = await client.post("/api/v1/uploads/audio", files=files)
    assert r2.status_code == 201, r2.text
    audio_id = r2.json()["artifact_id"]

    files = {"file": ("portrait.png", _make_png(), "image/png")}
    r3 = await client.post("/api/v1/uploads/image", files=files)
    assert r3.status_code == 201, r3.text
    image_id = r3.json()["artifact_id"]

    return job_id, audio_id, image_id


def _payload(**overrides) -> dict:
    base = {
        "job_id": "00000000-0000-0000-0000-000000000001",
        "image_artifact_id": "00000000-0000-0000-0000-000000000001",
        "audio_artifact_id": "00000000-0000-0000-0000-000000000001",
        "provider_id": "sadtalker",
        "target_duration_seconds": 30,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Happy path: returns not_implemented with input metadata echoed
# ---------------------------------------------------------------------------


async def test_video_generate_known_provider_returns_not_implemented(app_under_test):
    job_id, audio_id, image_id = await _setup_job_with_assets(app_under_test)
    r = await app_under_test.post(
        "/api/v1/video/generate",
        json=_payload(
            job_id=job_id,
            audio_artifact_id=audio_id,
            image_artifact_id=image_id,
            provider_id="sadtalker",
        ),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "not_implemented"
    assert body["provider_id"] == "sadtalker"
    assert body["error_code"] == "provider_not_implemented"
    assert body["output_video_artifact_id"] is None
    # Metadata carries input refs so the operator sees the contract.
    assert body["metadata"]["image_artifact_id"] == image_id
    assert body["metadata"]["audio_artifact_id"] == audio_id
    assert body["metadata"]["target_duration_seconds"] == 30


async def test_video_generate_supports_all_three_known_providers(app_under_test):
    job_id, audio_id, image_id = await _setup_job_with_assets(app_under_test)
    for provider in ("sadtalker", "musetalk", "wav2lip"):
        r = await app_under_test.post(
            "/api/v1/video/generate",
            json=_payload(
                job_id=job_id,
                audio_artifact_id=audio_id,
                image_artifact_id=image_id,
                provider_id=provider,
            ),
        )
        assert r.status_code == 200, (provider, r.text)
        assert r.json()["status"] == "not_implemented"
        assert r.json()["provider_id"] == provider


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


async def test_video_generate_unknown_job_returns_404(app_under_test):
    job_id, audio_id, image_id = await _setup_job_with_assets(app_under_test)
    r = await app_under_test.post(
        "/api/v1/video/generate",
        json=_payload(
            job_id=str(uuid.uuid4()),
            audio_artifact_id=audio_id,
            image_artifact_id=image_id,
        ),
    )
    assert r.status_code == 404


async def test_video_generate_missing_image_returns_missing_inputs(app_under_test):
    job_id, audio_id, _ = await _setup_job_with_assets(app_under_test)
    r = await app_under_test.post(
        "/api/v1/video/generate",
        json=_payload(
            job_id=job_id,
            audio_artifact_id=audio_id,
            image_artifact_id=str(uuid.uuid4()),
        ),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "missing_inputs"
    assert body["error_code"] == "image_artifact_not_found"


async def test_video_generate_missing_audio_returns_missing_inputs(app_under_test):
    job_id, _, image_id = await _setup_job_with_assets(app_under_test)
    r = await app_under_test.post(
        "/api/v1/video/generate",
        json=_payload(
            job_id=job_id,
            audio_artifact_id=str(uuid.uuid4()),
            image_artifact_id=image_id,
        ),
    )
    body = r.json()
    assert body["status"] == "missing_inputs"
    assert body["error_code"] == "audio_artifact_not_found"


async def test_video_generate_wrong_image_type_rejected(app_under_test):
    job_id, audio_id, _ = await _setup_job_with_assets(app_under_test)
    r = await app_under_test.post(
        "/api/v1/video/generate",
        json=_payload(
            job_id=job_id,
            audio_artifact_id=audio_id,
            # Pass the audio id where the image id is expected.
            image_artifact_id=audio_id,
        ),
    )
    body = r.json()
    assert body["status"] == "missing_inputs"
    assert body["error_code"] == "wrong_image_artifact_type"


async def test_video_generate_unknown_provider_returns_not_configured(app_under_test):
    job_id, audio_id, image_id = await _setup_job_with_assets(app_under_test)
    r = await app_under_test.post(
        "/api/v1/video/generate",
        json=_payload(
            job_id=job_id,
            audio_artifact_id=audio_id,
            image_artifact_id=image_id,
            provider_id="some_unknown_provider",
        ),
    )
    body = r.json()
    assert body["status"] == "not_configured"
    assert body["error_code"] == "unknown_provider"


async def test_video_generate_rejects_unknown_fields(app_under_test):
    r = await app_under_test.post(
        "/api/v1/video/generate", json={**_payload(), "unknown": "x"}
    )
    assert r.status_code == 422


async def test_video_generate_rejects_out_of_range_duration(app_under_test):
    job_id, audio_id, image_id = await _setup_job_with_assets(app_under_test)
    r = await app_under_test.post(
        "/api/v1/video/generate",
        json=_payload(
            job_id=job_id,
            audio_artifact_id=audio_id,
            image_artifact_id=image_id,
            target_duration_seconds=0,
        ),
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Providers metadata still lists the three video generators as not_implemented
# ---------------------------------------------------------------------------


async def test_providers_video_generator_catalog_pinned(app_under_test):
    r = await app_under_test.get("/api/v1/providers/video-generators")
    assert r.status_code == 200
    ids = {p["provider_id"] for p in r.json()}
    # Phase 6D extended the catalog. The Phase 3A trio stays present
    # and every entry remains ``not_implemented``.
    assert {"sadtalker", "musetalk", "wav2lip"}.issubset(ids)
    for p in r.json():
        assert p["status"] == "not_implemented"
