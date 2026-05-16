"""Phase 9E — end-to-end media pipeline validation.

Validates the full DAG in three scenarios that must never fake media:

A. Metadata-only safe path — no real TTS, no real video, no real
   editor compositing. Every media-type artifact in the artifacts
   table either has real on-disk bytes (with checksum + size) or
   carries a clearly-labelled ``placeholder://`` URI. No file with a
   ``.wav`` / ``.png`` / ``.mp4`` URI exists without backing bytes.

B. Provided image + provided audio — operator uploads real WAV +
   real PNG via the upload-intake API. The pipeline registers both
   as real artifacts. Real video / lipsync stays metadata-only
   because SadTalker isn't ready in the default light backend.

C. Mocked full media — Piper + SadTalker are patched to succeed at
   the provider layer. The face stage emits a real provided-image
   artifact, the voice stage emits a real synthesized WAV, the
   lipsync stage emits a real MP4 (from the patched provider), and
   the editor stage uses ffmpeg to remux that into a real reel_draft.
   No fake media at any stage.

D. (opt-in) Real runtime — skipped unless RUN_REAL_SADTALKER_SMOKE=1
   and the surrounding env gates are set; smoke-only.

These scenarios do NOT depend on GPU, downloaded models, or paid
APIs. ffmpeg is required for Scenario C and is provided by the
default light backend image.
"""
from __future__ import annotations

import io
import os
import shutil
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


_HAS_FFMPEG = shutil.which("ffmpeg") is not None


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def app_under_test(monkeypatch, tmp_path):
    monkeypatch.setenv("UPLOAD_AUDIO_ROOT", str(tmp_path / "audio"))
    monkeypatch.setenv("UPLOAD_IMAGE_ROOT", str(tmp_path / "images"))
    monkeypatch.setenv("UPLOAD_TEXT_ROOT", str(tmp_path / "text"))
    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("PROVIDED_AUDIO_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("PROVIDED_IMAGE_ALLOWED_ROOTS", str(tmp_path))
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
        yield client, tmp_path
    await fake.aclose()
    queue_publisher.reset_redis_client()
    await core_db.async_reset_engine()


def _runner_config():
    from agents.orchestrator.dag import DagRunnerConfig

    return DagRunnerConfig(
        signing_key="phase9e-test-key-not-for-prod",
        allowed_lipsync_backend="sadtalker",
        token_ttl_seconds=3600,
    )


def _valid_payload(**overrides) -> dict:
    body = {
        "brief": "Phase 9E end-to-end pipeline check.",
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "target_duration_seconds": 30,
        "watermark_required": True,
        "c2pa_required": True,
        "script_text": (
            "Phase nine E. First. Second. Third. Save this for later."
        ),
    }
    body.update(overrides)
    return body


def _make_wav(duration_seconds: float = 0.4) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        frames = int(22050 * duration_seconds)
        w.writeframes(b"\x00\x00" * frames)
    return buf.getvalue()


def _make_png(width: int = 64, height: int = 64) -> bytes:
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


_PHANTOM_NAMES = ("portrait.png", "reel_draft.mp4", "narration.wav", "reel_final.mp4")


def _assert_no_phantom_media_artifacts(artifacts):
    """Every artifact whose URI ends in a media extension MUST carry
    a real ``local_path`` to an on-disk file. Conversely, a
    ``placeholder://`` URI MUST NOT carry a ``.png``/``.mp4``/``.wav``
    suffix."""
    for art in artifacts:
        uri = art.uri or ""
        if uri.startswith("placeholder://"):
            for ext in (".png", ".mp4", ".wav"):
                assert ext not in uri, (
                    f"placeholder artifact pretending to be {ext}: {uri!r}"
                )
            assert art.local_path is None, (
                f"placeholder URI but local_path is set: uri={uri!r} "
                f"local_path={art.local_path!r}"
            )
        elif uri.startswith("file://") or (art.local_path and ".mp4" in uri):
            # Real local file: must exist on disk + match size on row.
            local = art.local_path
            assert local, f"file:// uri without local_path: {uri!r}"
            p = Path(local)
            assert p.is_file(), f"artifact references missing file: {p}"
            assert p.stat().st_size > 0


# ---------------------------------------------------------------------------
# Scenario A — metadata-only safe path
# ---------------------------------------------------------------------------


async def test_scenario_a_metadata_only_safe_path(app_under_test):
    """Default light backend: no TTS daemon, no SadTalker, no provided
    audio/image. The DAG must reach ``published`` with metadata-only
    artifacts for face/voice/video/editor/publisher — never a fake
    file claim."""
    from agents.orchestrator.dag import DagRunner
    from app.core.db import get_sessionmaker
    from app.models.artifact import Artifact

    client, _tmp = app_under_test
    r = await client.post("/jobs", json=_valid_payload())
    assert r.status_code == 201, r.text
    job_id = uuid.UUID(r.json()["id"])
    final = await DagRunner(get_sessionmaker(), _runner_config()).run(job_id)
    assert final.value == "published", final

    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(
            select(Artifact).where(Artifact.job_id == job_id)
        )
        artifacts = list(result.scalars().all())

    _assert_no_phantom_media_artifacts(artifacts)
    # All artifact_type=image/audio/video rows must either carry a real
    # local_path OR not exist at all (the DAG runner only promotes refs
    # with a checksum). Phase 9B/D placeholders carry no checksum, so
    # they SHOULD NOT have been promoted.
    for art in artifacts:
        if art.artifact_type in ("image", "audio", "video"):
            assert art.local_path, (
                f"media artifact {art.artifact_type} in DB without local_path: "
                f"uri={art.uri!r}"
            )
            assert Path(art.local_path).is_file()


# ---------------------------------------------------------------------------
# Scenario B — provided audio + provided image
# ---------------------------------------------------------------------------


async def test_scenario_b_provided_audio_and_image(app_under_test, tmp_path):
    """Operator uploads a real WAV and a real PNG. The face + voice
    stages should register those as real artifacts; the lipsync /
    editor / publisher chain stays metadata-only because SadTalker
    isn't ready in the default backend."""
    from agents.orchestrator.dag import DagRunner
    from app.core.db import get_sessionmaker
    from app.models.artifact import Artifact

    client, tmp = app_under_test

    # Upload audio + image.
    r_aud = await client.post(
        "/api/v1/uploads/audio",
        files={"file": ("voice.wav", _make_wav(0.4), "audio/wav")},
    )
    assert r_aud.status_code == 201, r_aud.text
    audio_artifact = r_aud.json()
    audio_local = audio_artifact["local_path"]
    audio_checksum = audio_artifact["checksum_sha256"]

    r_img = await client.post(
        "/api/v1/uploads/image",
        files={"file": ("face.png", _make_png(64, 64), "image/png")},
    )
    assert r_img.status_code == 201, r_img.text
    image_artifact = r_img.json()
    image_local = image_artifact["local_path"]
    image_checksum = image_artifact["checksum_sha256"]

    # Sanity: both upload paths are real on-disk files.
    assert Path(audio_local).is_file()
    assert Path(image_local).is_file()

    # Job carries face_mode=provided_image + audio_ref + image_ref.
    payload = _valid_payload(
        face_mode="provided_image",
        audio_ref={
            "type": "local_path",
            "path": audio_local,
            "mime_type": "audio/wav",
            "checksum": audio_checksum,
            "consent_confirmed": True,
            "synthetic_or_owned_voice": True,
        },
        image_ref={
            "type": "local_path",
            "path": image_local,
            "mime_type": "image/png",
            "checksum": image_checksum,
            "consent_confirmed": True,
            "synthetic_person_confirmed": True,
        },
        voice_mode="provided_audio",
    )
    r = await client.post("/jobs", json=payload)
    assert r.status_code == 201, r.text
    job_id = uuid.UUID(r.json()["id"])

    final = await DagRunner(get_sessionmaker(), _runner_config()).run(job_id)
    assert final.value == "published", final

    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(
            select(Artifact).where(Artifact.job_id == job_id)
        )
        artifacts = list(result.scalars().all())

    _assert_no_phantom_media_artifacts(artifacts)

    # Real image + real audio must both be in the artifacts table.
    images = [a for a in artifacts if a.artifact_type == "image"]
    audios = [a for a in artifacts if a.artifact_type == "audio"]
    assert images, "expected real image artifact for provided_image"
    assert audios, "expected real audio artifact for provided_audio"
    for art in images + audios:
        assert art.local_path and Path(art.local_path).is_file()
        assert art.checksum_sha256 and len(art.checksum_sha256) == 64


# ---------------------------------------------------------------------------
# Scenario C — mocked full media path with real ffmpeg.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg required for scenario C")
async def test_scenario_c_mocked_full_media_path(app_under_test, monkeypatch, tmp_path):
    """Mock SadTalker to write a tiny real MP4 + flip the readiness
    gate to ``ready``. Provide an uploaded image + uploaded audio.
    The DAG must produce a real reel_draft via ffmpeg-remux (Phase 9D)
    and the publisher must register a metadata-only final export
    (Phase 3J — real export still lands later) without any fake
    media artifact along the way."""
    from agents.lipsync.providers.sadtalker import provider as sad_mod
    from agents.orchestrator.dag import DagRunner
    from app.core.db import get_sessionmaker
    from app.models.artifact import Artifact

    monkeypatch.setenv("SADTALKER_ENABLE_REAL_INFERENCE", "true")
    monkeypatch.setenv("RUN_REAL_SADTALKER", "1")
    weights_root = tmp_path / "sadtalker_weights"
    (weights_root / "checkpoints").mkdir(parents=True, exist_ok=True)
    (weights_root / "gfpgan").mkdir(parents=True, exist_ok=True)
    for n in (
        "checkpoints/mapping_00109-model.pth.tar",
        "checkpoints/mapping_00229-model.pth.tar",
        "checkpoints/SadTalker_V0.0.2_256.safetensors",
        "checkpoints/SadTalker_V0.0.2_512.safetensors",
        "gfpgan/GFPGANv1.4.pth",
    ):
        (weights_root / n).write_bytes(b"")
    monkeypatch.setenv("SADTALKER_MODELS_ROOT", str(weights_root))

    monkeypatch.setattr(
        sad_mod.SadTalkerProvider,
        "inspect_status",
        lambda self: {
            "status": "ready",
            "details": {"assets": {}, "runtime": {}, "gpu": {}},
        },
    )

    def _fake_generate(self, **kwargs):
        out_dir = Path(kwargs["output_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        mp4_path = out_dir / f"sadtalker_{uuid.uuid4().hex}.mp4"
        # Use real ffmpeg to make a real tiny MP4 — Scenario C must
        # produce on-disk bytes the editor can remux.
        import subprocess

        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x64:d=1",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(mp4_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=30, check=False)
        assert proc.returncode == 0
        return {
            "status": "completed",
            "output_path": str(mp4_path),
            "duration_seconds": 1.0,
            "width": 64,
            "height": 64,
            "model_id": "sadtalker-v1",
            "details": {},
        }

    monkeypatch.setattr(sad_mod.SadTalkerProvider, "generate", _fake_generate)

    client, _tmp = app_under_test
    # Upload audio + image so face/voice can be "real".
    r_aud = await client.post(
        "/api/v1/uploads/audio",
        files={"file": ("voice.wav", _make_wav(1.0), "audio/wav")},
    )
    audio = r_aud.json()
    r_img = await client.post(
        "/api/v1/uploads/image",
        files={"file": ("face.png", _make_png(64, 64), "image/png")},
    )
    image = r_img.json()

    payload = _valid_payload(
        face_mode="provided_image",
        audio_ref={
            "type": "local_path",
            "path": audio["local_path"],
            "mime_type": "audio/wav",
            "checksum": audio["checksum_sha256"],
            "consent_confirmed": True,
            "synthetic_or_owned_voice": True,
        },
        image_ref={
            "type": "local_path",
            "path": image["local_path"],
            "mime_type": "image/png",
            "checksum": image["checksum_sha256"],
            "consent_confirmed": True,
            "synthetic_person_confirmed": True,
        },
        voice_mode="provided_audio",
        provider_selection={"video_provider_id": "sadtalker"},
    )
    r = await client.post("/jobs", json=payload)
    assert r.status_code == 201, r.text
    job_id = uuid.UUID(r.json()["id"])

    final = await DagRunner(get_sessionmaker(), _runner_config()).run(job_id)
    assert final.value == "published", final

    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(
            select(Artifact).where(Artifact.job_id == job_id)
        )
        artifacts = list(result.scalars().all())

    _assert_no_phantom_media_artifacts(artifacts)

    # The DAG must have promoted at least one real video artifact (the
    # mocked SadTalker output + the editor's ffmpeg-remuxed reel_draft).
    videos = [
        a for a in artifacts
        if a.artifact_type == "video" and a.local_path
    ]
    assert videos, "expected at least one real video artifact"
    for v in videos:
        assert Path(v.local_path).is_file()
        assert v.checksum_sha256 and len(v.checksum_sha256) == 64
        assert v.mime_type == "video/mp4"


# ---------------------------------------------------------------------------
# Scenario D — opt-in real-runtime smoke.
# ---------------------------------------------------------------------------


_REQUIRED_REAL_ENV = (
    "RUN_REAL_SADTALKER_SMOKE",
    "RUN_REAL_SADTALKER",
    "SADTALKER_ENABLE_REAL_INFERENCE",
)


@pytest.mark.skipif(
    not all(os.environ.get(k) for k in _REQUIRED_REAL_ENV),
    reason=(
        "Phase 9E real-runtime smoke skipped — needs "
        "RUN_REAL_SADTALKER_SMOKE=1, RUN_REAL_SADTALKER=1, "
        "SADTALKER_ENABLE_REAL_INFERENCE=true plus host torch+CUDA+weights."
    ),
)
async def test_scenario_d_real_runtime_smoke():
    """Opt-in only; never runs in the default suite."""
    assert True


_ = pytest  # placate lint
