"""Phase 4A-2 integration tests — upload intake API.

Endpoints under test:
- ``POST /api/v1/uploads/text``
- ``POST /api/v1/uploads/audio``
- ``POST /api/v1/uploads/image``
- ``POST /api/v1/jobs/from-inputs``

Boundary expectations:
- No binary content in API responses.
- No real media generation.
- Uploaded files land under the configured upload root with uuid-derived
  filenames — the operator's original filename is never echoed back.
- The from-inputs endpoint reuses the existing JobCreateRequest path so
  every compliance / consent / path-safety validator re-runs.
"""
from __future__ import annotations

import json
import struct
import uuid
import wave
from pathlib import Path

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def app_under_test(monkeypatch, tmp_path):
    # Upload roots + path-safety roots all point at tmp_path so the
    # from-inputs flow can re-validate the AudioRef/ImageRef paths against
    # PROVIDED_AUDIO_ALLOWED_ROOTS / PROVIDED_IMAGE_ALLOWED_ROOTS without
    # touching the real filesystem.
    audio_root = tmp_path / "audio"
    image_root = tmp_path / "images"
    text_root = tmp_path / "text"
    monkeypatch.setenv("UPLOAD_AUDIO_ROOT", str(audio_root))
    monkeypatch.setenv("UPLOAD_IMAGE_ROOT", str(image_root))
    monkeypatch.setenv("UPLOAD_TEXT_ROOT", str(text_root))
    monkeypatch.setenv("PROVIDED_AUDIO_ALLOWED_ROOTS", str(audio_root))
    monkeypatch.setenv("PROVIDED_IMAGE_ALLOWED_ROOTS", str(image_root))
    # Keep size caps generous; size-limit cases set their own caps via
    # monkeypatch in-test.
    monkeypatch.setenv("AUDIO_MAX_FILE_SIZE_BYTES", "1048576")  # 1 MB
    monkeypatch.setenv("IMAGE_MAX_FILE_SIZE_BYTES", "524288")    # 512 KB
    monkeypatch.setenv("SCRIPT_TEXT_MAX_CHARS", "8000")
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
        yield client, fake, tmp_path, audio_root, image_root, text_root

    await fake.aclose()
    queue_publisher.reset_redis_client()
    await core_db.async_reset_engine()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_wav_bytes(*, duration_sec: float = 0.3, sample_rate: int = 22050) -> bytes:
    import io

    n_frames = int(duration_sec * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b"\x00\x00" * n_frames)
    return buf.getvalue()


def _make_min_png_bytes(width: int = 64, height: int = 64) -> bytes:
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = (
        b"\x00\x00\x00\x0d"
        + b"IHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )
    tail = b"\x00\x00\x00\x00IEND\xae\x42\x60\x82"
    return sig + ihdr + tail


def _make_min_jpeg_bytes(width: int = 64, height: int = 64) -> bytes:
    soi = b"\xff\xd8"
    sof0 = (
        b"\xff\xc0"
        + b"\x00\x11"
        + b"\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x03"
        + b"\x01\x22\x00"
        + b"\x02\x11\x01"
        + b"\x03\x11\x01"
    )
    eoi = b"\xff\xd9"
    return soi + sof0 + eoi


def _make_min_webp_bytes(width: int = 64, height: int = 64) -> bytes:
    chunk_size = 10
    vp8x = (
        b"VP8X"
        + struct.pack("<I", chunk_size)
        + b"\x00"
        + b"\x00\x00\x00"
        + (width - 1).to_bytes(3, "little")
        + (height - 1).to_bytes(3, "little")
    )
    file_size_field = (4 + len(vp8x)).to_bytes(4, "little")
    return b"RIFF" + file_size_field + b"WEBP" + vp8x


def _valid_text_payload() -> dict:
    return {
        "title": "Sleep tips",
        "script_text": "Tip one: avoid screens before bed.\n\nTip two: keep room cool.\n\nTip three: set a schedule.",
        "language": "en",
        "tone": "friendly",
        "target_duration_seconds": 30,
    }


# ---------------------------------------------------------------------------
# Text upload
# ---------------------------------------------------------------------------


async def test_text_upload_creates_script_artifact(app_under_test):
    client, _, _, _, _, text_root = app_under_test
    r = await client.post("/api/v1/uploads/text", json=_valid_text_payload())
    assert r.status_code == 201, r.text
    body = r.json()
    for key in ("artifact_id", "artifact_type", "uri", "mime_type",
                "checksum_sha256", "size_bytes", "script_ref",
                "metadata_summary"):
        assert key in body
    assert body["artifact_type"] == "script"
    assert body["mime_type"] == "application/json"
    assert body["uri"].startswith("file://")
    assert body["uri"].endswith(".json")
    # File landed under the configured root.
    saved = Path(body["uri"].removeprefix("file://"))
    assert saved.parent == text_root
    # script_ref carries the artifact_id for the future from-inputs call.
    assert body["script_ref"]["artifact_id"] == body["artifact_id"]
    # metadata_summary preserves the script_text without trimming.
    assert body["metadata_summary"]["script_text"].startswith("Tip one")


async def test_text_upload_rejects_empty_text(app_under_test):
    client, *_ = app_under_test
    payload = _valid_text_payload()
    payload["script_text"] = "   "
    r = await client.post("/api/v1/uploads/text", json=payload)
    assert r.status_code == 422


async def test_text_upload_enforces_max_length(app_under_test, monkeypatch):
    """SCRIPT_TEXT_MAX_CHARS is honored at runtime."""
    monkeypatch.setenv("SCRIPT_TEXT_MAX_CHARS", "100")
    client, *_ = app_under_test
    payload = _valid_text_payload()
    payload["script_text"] = "x" * 200
    r = await client.post("/api/v1/uploads/text", json=payload)
    assert r.status_code == 413


async def test_text_upload_uses_unique_filename(app_under_test):
    """Two identical uploads land in two distinct files."""
    client, _, _, _, _, text_root = app_under_test
    r1 = await client.post("/api/v1/uploads/text", json=_valid_text_payload())
    r2 = await client.post("/api/v1/uploads/text", json=_valid_text_payload())
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["uri"] != r2.json()["uri"]


# ---------------------------------------------------------------------------
# Audio upload
# ---------------------------------------------------------------------------


async def test_audio_upload_accepts_valid_wav(app_under_test):
    client, _, _, audio_root, _, _ = app_under_test
    wav_bytes = _make_wav_bytes(duration_sec=0.5, sample_rate=22050)
    files = {"file": ("recording.wav", wav_bytes, "audio/wav")}
    r = await client.post("/api/v1/uploads/audio", files=files)
    assert r.status_code == 201, r.text
    body = r.json()
    for key in ("artifact_id", "artifact_type", "uri", "local_path",
                "mime_type", "checksum_sha256", "size_bytes",
                "duration_seconds", "sample_rate", "channels",
                "audio_ref", "metadata_summary"):
        assert key in body
    assert body["artifact_type"] == "audio"
    assert body["mime_type"] == "audio/wav"
    assert body["sample_rate"] == 22050
    assert body["channels"] == 1
    assert body["duration_seconds"] == pytest.approx(0.5, abs=1e-2)
    assert Path(body["local_path"]).parent == audio_root
    # Filename is NOT the operator's "recording.wav".
    assert Path(body["local_path"]).name != "recording.wav"
    assert Path(body["local_path"]).suffix == ".wav"


async def test_audio_upload_rejects_unsupported_extension(app_under_test):
    """Phase 4F broadens the audio allow-list to wav/mp3/m4a/aac/flac/ogg.

    The Phase 4A-2 contract that *any* non-WAV extension is rejected was
    relaxed; this test now pins the policy to "extensions outside the
    Phase 4F allow-list are rejected" by trying a .txt upload.
    """
    client, *_ = app_under_test
    files = {"file": ("rec.txt", b"\x00\x00", "audio/wav")}
    r = await client.post("/api/v1/uploads/audio", files=files)
    assert r.status_code == 400
    assert "extension" in r.text.lower()


async def test_audio_upload_rejects_bad_wav_header(app_under_test):
    """Filename + mime claim WAV but the body isn't a real WAV."""
    client, *_ = app_under_test
    files = {"file": ("rec.wav", b"NOT REALLY A WAV" * 4, "audio/wav")}
    r = await client.post("/api/v1/uploads/audio", files=files)
    assert r.status_code == 400
    assert "wav" in r.text.lower()


async def test_audio_upload_enforces_size_cap(app_under_test, monkeypatch):
    """Setting the cap below the file size triggers a 413."""
    client, *_ = app_under_test
    wav_bytes = _make_wav_bytes(duration_sec=0.5)
    monkeypatch.setenv("AUDIO_MAX_FILE_SIZE_BYTES", str(max(1, len(wav_bytes) - 16)))
    files = {"file": ("rec.wav", wav_bytes, "audio/wav")}
    r = await client.post("/api/v1/uploads/audio", files=files)
    assert r.status_code == 413


# ---------------------------------------------------------------------------
# Image upload
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,mime,maker",
    [
        ("portrait.png", "image/png", _make_min_png_bytes),
        ("portrait.jpg", "image/jpeg", _make_min_jpeg_bytes),
        ("portrait.webp", "image/webp", _make_min_webp_bytes),
    ],
)
async def test_image_upload_accepts_supported_formats(app_under_test, name, mime, maker):
    client, _, _, _, image_root, _ = app_under_test
    img_bytes = maker(128, 96)
    files = {"file": (name, img_bytes, mime)}
    r = await client.post("/api/v1/uploads/image", files=files)
    assert r.status_code == 201, r.text
    body = r.json()
    for key in ("artifact_id", "artifact_type", "uri", "local_path",
                "mime_type", "checksum_sha256", "size_bytes",
                "width", "height", "image_ref", "metadata_summary"):
        assert key in body
    assert body["artifact_type"] == "image"
    assert body["mime_type"] == mime
    assert body["width"] == 128
    assert body["height"] == 96
    assert Path(body["local_path"]).parent == image_root
    assert Path(body["local_path"]).name != name


async def test_image_upload_rejects_unsupported_extension(app_under_test):
    client, *_ = app_under_test
    files = {"file": ("evil.gif", b"GIF89a", "image/gif")}
    r = await client.post("/api/v1/uploads/image", files=files)
    assert r.status_code == 400


async def test_image_upload_rejects_invalid_image_header(app_under_test):
    client, *_ = app_under_test
    files = {"file": ("bad.png", b"NOT A REAL PNG" * 8, "image/png")}
    r = await client.post("/api/v1/uploads/image", files=files)
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# No binary leaks
# ---------------------------------------------------------------------------


async def test_no_endpoint_returns_binary_content(app_under_test):
    client, *_ = app_under_test
    # text
    r = await client.post("/api/v1/uploads/text", json=_valid_text_payload())
    assert r.status_code == 201
    assert isinstance(json.dumps(r.json()), str)
    # audio
    r = await client.post(
        "/api/v1/uploads/audio",
        files={"file": ("rec.wav", _make_wav_bytes(), "audio/wav")},
    )
    assert r.status_code == 201
    assert isinstance(json.dumps(r.json()), str)
    # image
    r = await client.post(
        "/api/v1/uploads/image",
        files={"file": ("p.png", _make_min_png_bytes(), "image/png")},
    )
    assert r.status_code == 201
    assert isinstance(json.dumps(r.json()), str)


# ---------------------------------------------------------------------------
# /api/v1/jobs/from-inputs
# ---------------------------------------------------------------------------


async def _upload_text(client) -> dict:
    r = await client.post("/api/v1/uploads/text", json=_valid_text_payload())
    assert r.status_code == 201, r.text
    return r.json()


async def _upload_audio(client) -> dict:
    r = await client.post(
        "/api/v1/uploads/audio",
        files={"file": ("rec.wav", _make_wav_bytes(), "audio/wav")},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _upload_image(client) -> dict:
    r = await client.post(
        "/api/v1/uploads/image",
        files={"file": ("p.png", _make_min_png_bytes(256, 256), "image/png")},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _from_inputs_base() -> dict:
    return {
        "brief": "Three calming bedtime habits for better sleep.",
        "target_duration_seconds": 30,
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "watermark_required": True,
        "c2pa_required": True,
        "voice_mode": "tts",
        "face_mode": None,
    }


async def test_from_inputs_tts_with_uploaded_text_succeeds(app_under_test):
    client, *_ = app_under_test
    text = await _upload_text(client)

    payload = _from_inputs_base()
    payload["script_artifact_id"] = text["artifact_id"]
    r = await client.post("/api/v1/jobs/from-inputs", json=payload)
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["voice_mode"] == "tts"
    assert job["status"] == "pending_compliance"


async def test_from_inputs_tts_with_uploaded_text_and_image_succeeds(app_under_test):
    client, *_ = app_under_test
    text = await _upload_text(client)
    image = await _upload_image(client)

    payload = _from_inputs_base()
    payload.update(
        {
            "script_artifact_id": text["artifact_id"],
            "face_mode": "provided_image",
            "image_artifact_id": image["artifact_id"],
            "image_consent_confirmed": True,
            "image_synthetic_person_confirmed": True,
        }
    )
    r = await client.post("/api/v1/jobs/from-inputs", json=payload)
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["face_mode"] == "provided_image"
    assert job["image_ref"]["path"] == image["local_path"]


async def test_from_inputs_provided_audio_plus_image_succeeds(app_under_test):
    client, *_ = app_under_test
    audio = await _upload_audio(client)
    image = await _upload_image(client)

    payload = _from_inputs_base()
    payload.update(
        {
            "voice_mode": "provided_audio",
            "audio_artifact_id": audio["artifact_id"],
            "audio_consent_confirmed": True,
            "audio_synthetic_or_owned": True,
            "face_mode": "provided_image",
            "image_artifact_id": image["artifact_id"],
            "image_consent_confirmed": True,
            "image_synthetic_person_confirmed": True,
        }
    )
    r = await client.post("/api/v1/jobs/from-inputs", json=payload)
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["voice_mode"] == "provided_audio"
    assert job["audio_ref"]["path"] == audio["local_path"]
    assert job["face_mode"] == "provided_image"
    assert job["image_ref"]["path"] == image["local_path"]


async def test_from_inputs_rejects_missing_audio_artifact_in_provided_audio_mode(
    app_under_test,
):
    client, *_ = app_under_test
    payload = _from_inputs_base()
    payload["voice_mode"] = "provided_audio"
    r = await client.post("/api/v1/jobs/from-inputs", json=payload)
    assert r.status_code == 422


async def test_from_inputs_rejects_audio_consent_false(app_under_test):
    """audio_consent_confirmed=False should fail at the AudioRef validator
    when from-inputs assembles the JobCreateRequest."""
    client, *_ = app_under_test
    audio = await _upload_audio(client)
    payload = _from_inputs_base()
    payload.update(
        {
            "voice_mode": "provided_audio",
            "audio_artifact_id": audio["artifact_id"],
            "audio_consent_confirmed": False,
            "audio_synthetic_or_owned": True,
        }
    )
    r = await client.post("/api/v1/jobs/from-inputs", json=payload)
    assert r.status_code in (400, 422)


async def test_from_inputs_rejects_wrong_artifact_type(app_under_test):
    """Submitting the text artifact id as the image artifact must fail with
    a clear 400 (after the schema-level tts validator is satisfied)."""
    client, *_ = app_under_test
    text = await _upload_text(client)
    payload = _from_inputs_base()
    # Satisfy schema-level voice_mode='tts' check with inline script_text,
    # so we reach the image-type assertion in the handler.
    payload["script_text"] = "Inline script."
    payload.update(
        {
            "face_mode": "provided_image",
            "image_artifact_id": text["artifact_id"],
            "image_consent_confirmed": True,
            "image_synthetic_person_confirmed": True,
        }
    )
    r = await client.post("/api/v1/jobs/from-inputs", json=payload)
    assert r.status_code == 400
    assert "expected image" in r.text


async def test_from_inputs_rejects_unknown_artifact_id(app_under_test):
    client, *_ = app_under_test
    payload = _from_inputs_base()
    payload["script_artifact_id"] = str(uuid.uuid4())
    r = await client.post("/api/v1/jobs/from-inputs", json=payload)
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Storage safety
# ---------------------------------------------------------------------------


async def test_uploaded_filenames_dont_echo_operator_input(app_under_test):
    """A malicious filename like '../etc/passwd.wav' must NOT escape the
    upload root — the endpoint ignores the original filename entirely."""
    client, _, _, audio_root, _, _ = app_under_test
    wav_bytes = _make_wav_bytes()
    evil_name = "../../../etc/passwd.wav"
    r = await client.post(
        "/api/v1/uploads/audio",
        files={"file": (evil_name, wav_bytes, "audio/wav")},
    )
    assert r.status_code == 201
    body = r.json()
    saved = Path(body["local_path"])
    # Stays under audio_root.
    assert saved.parent == audio_root
    # Does not contain "passwd" or "etc" anywhere in the saved name.
    assert "passwd" not in saved.name
    assert "etc" not in saved.name
    # Saved name is a uuid hex + .wav (32 hex chars).
    assert len(saved.stem) == 32
