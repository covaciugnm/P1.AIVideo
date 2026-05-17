"""Phase 9C — real video end-to-end path.

The video API and the DAG lipsync handler already implement the
categorised readiness gate (Phase 7B/7D). Phase 9C re-pins the
"never fake an MP4" invariants and the error-code-to-status mapping
that the operator depends on.

Default test run never invokes real SadTalker. The real smoke is opt-in
via ``RUN_REAL_SADTALKER_SMOKE=1 + RUN_REAL_SADTALKER=1 +
SADTALKER_ENABLE_REAL_INFERENCE=true`` plus host-level torch+CUDA+weights.
"""
from __future__ import annotations

import io
import struct
import uuid
import wave
import zlib
from pathlib import Path

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


_REQUIRED_REAL_ENV = (
    "RUN_REAL_SADTALKER_SMOKE",
    "RUN_REAL_SADTALKER",
    "SADTALKER_ENABLE_REAL_INFERENCE",
)


def _make_wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\x00\x00" * 6615)
    return buf.getvalue()


def _make_png(width: int = 256, height: int = 256) -> bytes:
    # Phase 11E — bumped default from 64×64 to 256×256 so the
    # backend's image-suitability precheck (Phase 11E) doesn't
    # short-circuit these tests with ``video_face_image_too_small``.
    # The precheck refuses anything below 256×256 because SadTalker's
    # cropper cannot reliably find landmarks on smaller portraits.
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = b"IHDR" + struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr_chunk = (
        struct.pack(">I", 13) + ihdr + struct.pack(">I", zlib.crc32(ihdr) & 0xFFFFFFFF)
    )
    raw = b"".join(b"\x00" + b"\xFF\xFF\xFF" * width for _ in range(height))
    idat = b"IDAT" + zlib.compress(raw)
    idat_chunk = (
        struct.pack(">I", len(idat) - 4)
        + idat
        + struct.pack(">I", zlib.crc32(idat) & 0xFFFFFFFF)
    )
    iend_chunk = struct.pack(">I", 0) + b"IEND" + struct.pack(
        ">I", zlib.crc32(b"IEND") & 0xFFFFFFFF
    )
    return sig + ihdr_chunk + idat_chunk + iend_chunk


def _place_fake_weights(models_root: Path) -> None:
    (models_root / "checkpoints").mkdir(parents=True, exist_ok=True)
    for name in (
        "mapping_00109-model.pth.tar",
        "mapping_00229-model.pth.tar",
        "SadTalker_V0.0.2_256.safetensors",
        "SadTalker_V0.0.2_512.safetensors",
    ):
        (models_root / "checkpoints" / name).write_bytes(b"")
    (models_root / "gfpgan").mkdir(parents=True, exist_ok=True)
    (models_root / "gfpgan" / "GFPGANv1.4.pth").write_bytes(b"")


@pytest_asyncio.fixture
async def app_under_test(monkeypatch, tmp_path):
    monkeypatch.setenv("UPLOAD_AUDIO_ROOT", str(tmp_path / "audio"))
    monkeypatch.setenv("UPLOAD_IMAGE_ROOT", str(tmp_path / "images"))
    monkeypatch.setenv("UPLOAD_TEXT_ROOT", str(tmp_path / "text"))
    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("SCRIPTWRITER_BACKEND", "template")
    monkeypatch.delenv("SCRIPTWRITER_ENABLE_NETWORK_CALLS", raising=False)

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


async def _setup_real_inputs(client: AsyncClient) -> tuple[str, str, str]:
    """Create a job + upload real image + audio. Returns the IDs."""
    r = await client.post(
        "/api/v1/jobs",
        json={
            "brief": "phase 9c",
            "synthetic_person_confirmed": True,
            "consent_confirmed": True,
            "target_duration_seconds": 30,
            "watermark_required": True,
            "c2pa_required": True,
            "script_text": "phase 9c",
        },
    )
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]

    r2 = await client.post(
        "/api/v1/uploads/audio",
        files={"file": ("voice.wav", _make_wav(), "audio/wav")},
    )
    assert r2.status_code == 201, r2.text
    audio_id = r2.json()["artifact_id"]

    r3 = await client.post(
        "/api/v1/uploads/image",
        files={"file": ("face.png", _make_png(), "image/png")},
    )
    assert r3.status_code == 201, r3.text
    image_id = r3.json()["artifact_id"]
    return job_id, audio_id, image_id


# ---------------------------------------------------------------------------
# Phase 9C: input-validation error codes.
# ---------------------------------------------------------------------------


async def test_missing_image_artifact_returns_clear_error(app_under_test):
    job_id, audio_id, _image_id = await _setup_real_inputs(app_under_test)
    body = {
        "job_id": job_id,
        "image_artifact_id": str(uuid.uuid4()),  # not registered
        "audio_artifact_id": audio_id,
        "provider_id": "sadtalker",
        "target_duration_seconds": 30,
    }
    r = await app_under_test.post("/api/v1/video/generate", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "missing_inputs"
    assert data["error_code"] == "image_artifact_not_found"
    assert data["output_video_artifact_id"] is None


async def test_missing_audio_artifact_returns_clear_error(app_under_test):
    job_id, _audio_id, image_id = await _setup_real_inputs(app_under_test)
    body = {
        "job_id": job_id,
        "image_artifact_id": image_id,
        "audio_artifact_id": str(uuid.uuid4()),
        "provider_id": "sadtalker",
        "target_duration_seconds": 30,
    }
    r = await app_under_test.post("/api/v1/video/generate", json=body)
    data = r.json()
    assert data["status"] == "missing_inputs"
    assert data["error_code"] == "audio_artifact_not_found"
    assert data["output_video_artifact_id"] is None


async def test_wrong_artifact_type_rejected(app_under_test):
    """Pass an audio artifact ID as the image argument — must reject
    cleanly with ``wrong_image_artifact_type``."""
    job_id, audio_id, image_id = await _setup_real_inputs(app_under_test)
    body = {
        "job_id": job_id,
        "image_artifact_id": audio_id,  # WRONG: audio in image slot
        "audio_artifact_id": image_id,  # WRONG: image in audio slot
        "provider_id": "sadtalker",
        "target_duration_seconds": 30,
    }
    r = await app_under_test.post("/api/v1/video/generate", json=body)
    data = r.json()
    assert data["status"] == "missing_inputs"
    assert data["error_code"] in (
        "wrong_image_artifact_type",
        "wrong_audio_artifact_type",
    )
    assert data["output_video_artifact_id"] is None


async def test_unknown_provider_rejected(app_under_test):
    job_id, audio_id, image_id = await _setup_real_inputs(app_under_test)
    body = {
        "job_id": job_id,
        "image_artifact_id": image_id,
        "audio_artifact_id": audio_id,
        "provider_id": "definitely_not_a_provider",
        "target_duration_seconds": 30,
    }
    r = await app_under_test.post("/api/v1/video/generate", json=body)
    data = r.json()
    assert data["error_code"] == "unknown_provider"
    assert data["status"] == "not_configured"
    assert data["output_video_artifact_id"] is None


# ---------------------------------------------------------------------------
# Phase 9C: categorised readiness gates.
# ---------------------------------------------------------------------------


async def test_default_state_returns_provider_not_implemented(app_under_test):
    """Without ``RUN_REAL_SADTALKER=1`` + ``SADTALKER_ENABLE_REAL_INFERENCE=true``,
    SadTalker's inspect_status() returns ``not_implemented``. The video
    API must surface ``provider_not_implemented`` — never ``completed``,
    never a phantom artifact."""
    job_id, audio_id, image_id = await _setup_real_inputs(app_under_test)
    body = {
        "job_id": job_id,
        "image_artifact_id": image_id,
        "audio_artifact_id": audio_id,
        "provider_id": "sadtalker",
        "target_duration_seconds": 30,
    }
    r = await app_under_test.post("/api/v1/video/generate", json=body)
    data = r.json()
    assert data["status"] == "not_implemented"
    assert data["error_code"] == "provider_not_implemented"
    assert data["output_video_artifact_id"] is None


async def test_runtime_missing_surfaces_video_runtime_missing(
    app_under_test, monkeypatch, tmp_path
):
    """Flags on, weights present, but torch is not importable → the
    API must return ``error_code='video_runtime_missing'``."""
    monkeypatch.setenv("SADTALKER_ENABLE_REAL_INFERENCE", "true")
    monkeypatch.setenv("RUN_REAL_SADTALKER", "1")
    models_root = tmp_path / "weights"
    _place_fake_weights(models_root)
    monkeypatch.setenv("SADTALKER_MODELS_ROOT", str(models_root))

    from agents.lipsync.providers.sadtalker import provider as sad_mod

    monkeypatch.setattr(
        sad_mod.SadTalkerProvider,
        "inspect_status",
        lambda self: {
            "status": "runtime_missing",
            "details": {
                "runtime": {"torch_available": False},
                "assets": {"status": "ok"},
                "gpu": {"available": False},
            },
        },
    )

    job_id, audio_id, image_id = await _setup_real_inputs(app_under_test)
    r = await app_under_test.post(
        "/api/v1/video/generate",
        json={
            "job_id": job_id,
            "image_artifact_id": image_id,
            "audio_artifact_id": audio_id,
            "provider_id": "sadtalker",
            "target_duration_seconds": 30,
        },
    )
    data = r.json()
    assert data["error_code"] == "video_runtime_missing"
    assert data["output_video_artifact_id"] is None


async def test_assets_missing_surfaces_video_assets_missing(
    app_under_test, monkeypatch, tmp_path
):
    monkeypatch.setenv("SADTALKER_ENABLE_REAL_INFERENCE", "true")
    monkeypatch.setenv("RUN_REAL_SADTALKER", "1")
    monkeypatch.setenv("SADTALKER_MODELS_ROOT", str(tmp_path / "empty_weights"))

    from agents.lipsync.providers.sadtalker import provider as sad_mod

    monkeypatch.setattr(
        sad_mod.SadTalkerProvider,
        "inspect_status",
        lambda self: {
            "status": "assets_missing",
            "details": {
                "assets": {"missing": ["checkpoints/SadTalker_V0.0.2_512.safetensors"]},
                "runtime": {"torch_available": True},
                "gpu": {"available": True},
            },
        },
    )
    job_id, audio_id, image_id = await _setup_real_inputs(app_under_test)
    r = await app_under_test.post(
        "/api/v1/video/generate",
        json={
            "job_id": job_id,
            "image_artifact_id": image_id,
            "audio_artifact_id": audio_id,
            "provider_id": "sadtalker",
            "target_duration_seconds": 30,
        },
    )
    data = r.json()
    assert data["error_code"] == "video_assets_missing"
    assert data["output_video_artifact_id"] is None


async def test_gpu_unavailable_surfaces_video_gpu_missing(
    app_under_test, monkeypatch, tmp_path
):
    monkeypatch.setenv("SADTALKER_ENABLE_REAL_INFERENCE", "true")
    monkeypatch.setenv("RUN_REAL_SADTALKER", "1")
    _place_fake_weights(tmp_path / "weights")
    monkeypatch.setenv("SADTALKER_MODELS_ROOT", str(tmp_path / "weights"))

    from agents.lipsync.providers.sadtalker import provider as sad_mod

    monkeypatch.setattr(
        sad_mod.SadTalkerProvider,
        "inspect_status",
        lambda self: {
            "status": "gpu_unavailable",
            "details": {
                "assets": {"status": "ok"},
                "runtime": {"torch_available": True},
                "gpu": {"available": False, "device_count": 0},
            },
        },
    )
    job_id, audio_id, image_id = await _setup_real_inputs(app_under_test)
    r = await app_under_test.post(
        "/api/v1/video/generate",
        json={
            "job_id": job_id,
            "image_artifact_id": image_id,
            "audio_artifact_id": audio_id,
            "provider_id": "sadtalker",
            "target_duration_seconds": 30,
        },
    )
    data = r.json()
    assert data["error_code"] == "video_gpu_missing"
    assert data["output_video_artifact_id"] is None


async def test_not_configured_surfaces_video_provider_not_configured(
    app_under_test, monkeypatch
):
    """Real inference flags on but SADTALKER_MODELS_ROOT unset → not_configured."""
    monkeypatch.setenv("SADTALKER_ENABLE_REAL_INFERENCE", "true")
    monkeypatch.setenv("RUN_REAL_SADTALKER", "1")
    monkeypatch.delenv("SADTALKER_MODELS_ROOT", raising=False)

    from agents.lipsync.providers.sadtalker import provider as sad_mod

    monkeypatch.setattr(
        sad_mod.SadTalkerProvider,
        "inspect_status",
        lambda self: {
            "status": "not_configured",
            "details": {"reason": "SADTALKER_MODELS_ROOT unset"},
        },
    )
    job_id, audio_id, image_id = await _setup_real_inputs(app_under_test)
    r = await app_under_test.post(
        "/api/v1/video/generate",
        json={
            "job_id": job_id,
            "image_artifact_id": image_id,
            "audio_artifact_id": audio_id,
            "provider_id": "sadtalker",
            "target_duration_seconds": 30,
        },
    )
    data = r.json()
    assert data["error_code"] == "video_provider_not_configured"
    assert data["output_video_artifact_id"] is None


# ---------------------------------------------------------------------------
# Phase 9C: provider reports success but file missing → no fake registration.
# ---------------------------------------------------------------------------


async def test_provider_reports_success_but_file_missing_does_not_register(
    app_under_test, monkeypatch, tmp_path
):
    """SadTalker says completed but the path it returned doesn't exist:
    the API must refuse to register a phantom artifact and return
    ``video_generation_failed`` instead."""
    monkeypatch.setenv("SADTALKER_ENABLE_REAL_INFERENCE", "true")
    monkeypatch.setenv("RUN_REAL_SADTALKER", "1")
    _place_fake_weights(tmp_path / "weights")
    monkeypatch.setenv("SADTALKER_MODELS_ROOT", str(tmp_path / "weights"))

    from agents.lipsync.providers.sadtalker import provider as sad_mod

    monkeypatch.setattr(
        sad_mod.SadTalkerProvider,
        "inspect_status",
        lambda self: {
            "status": "ready",
            "details": {"assets": {}, "runtime": {}, "gpu": {}},
        },
    )

    def _liar(self, **kwargs):
        # Reports "completed" but the file we point at does NOT exist.
        return {
            "status": "completed",
            "output_path": str(tmp_path / "phantom" / "ghost.mp4"),
            "duration_seconds": 3.0,
            "details": {},
        }

    monkeypatch.setattr(sad_mod.SadTalkerProvider, "generate", _liar)

    job_id, audio_id, image_id = await _setup_real_inputs(app_under_test)
    r = await app_under_test.post(
        "/api/v1/video/generate",
        json={
            "job_id": job_id,
            "image_artifact_id": image_id,
            "audio_artifact_id": audio_id,
            "provider_id": "sadtalker",
            "target_duration_seconds": 30,
        },
    )
    data = r.json()
    assert data["error_code"] == "video_generation_failed"
    assert data["status"] == "failed"
    assert data["output_video_artifact_id"] is None

    # And there must be NO video Artifact row for this job.
    from app.core.db import get_sessionmaker
    from app.models.artifact import Artifact

    sm = get_sessionmaker()
    async with sm() as session:
        rows = await session.execute(
            select(Artifact).where(
                Artifact.job_id == uuid.UUID(job_id),
                Artifact.artifact_type == "video",
            )
        )
        assert rows.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# Phase 9C: optional real smoke (skipped by default).
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not all(__import__("os").environ.get(k) for k in _REQUIRED_REAL_ENV),
    reason=(
        "Phase 9C real SadTalker smoke skipped — needs "
        "RUN_REAL_SADTALKER_SMOKE=1, RUN_REAL_SADTALKER=1, "
        "SADTALKER_ENABLE_REAL_INFERENCE=true plus host torch+CUDA+weights."
    ),
)
async def test_real_sadtalker_smoke(app_under_test):
    """Opt-in only — never runs in CI / default `make test`."""
    job_id, audio_id, image_id = await _setup_real_inputs(app_under_test)
    r = await app_under_test.post(
        "/api/v1/video/generate",
        json={
            "job_id": job_id,
            "image_artifact_id": image_id,
            "audio_artifact_id": audio_id,
            "provider_id": "sadtalker",
            "target_duration_seconds": 5,
        },
    )
    data = r.json()
    assert data["status"] == "completed", data
    assert data["output_video_artifact_id"] is not None


_ = pytest  # placate lint
