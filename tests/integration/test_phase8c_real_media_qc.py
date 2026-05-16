"""Phase 8C — real media QC.

Default-suite tests cover:

- Metadata-only QC path is **untouched** by Phase 8C (Phase 3I tests
  still green; pinned here by a content sanity check).
- ``inspect_media_artifact()`` direct calls:
  - relative path / missing file / zero bytes → categorised failures.
  - bogus container (ffprobe-gated) → ``ffprobe_inspection`` failure.
  - real tiny MP4 (ffmpeg-gated) → ``passed=True`` + populated fields.
  - duration delta warn / fail thresholds.
  - checksum mismatch fails.
  - missing audio warns when ``require_audio=False``, fails when True.
- ``/api/v1/qc/inspect`` endpoint:
  - 404 on unknown job.
  - ``missing_inputs`` / ``media_artifact_missing`` when no video.
  - ``wrong_artifact_type`` on an audio-id mistaken for video.
  - safe-path / allowed-roots gates.
  - real success path returns a populated ``report`` block.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient


_HAS_FFMPEG = shutil.which("ffmpeg") is not None
_HAS_FFPROBE = shutil.which("ffprobe") is not None


# ---------------------------------------------------------------------------
# inspect_media_artifact — direct unit-style tests
# ---------------------------------------------------------------------------


def test_inspect_rejects_relative_path():
    from app.services.media_qc import inspect_media_artifact

    r = inspect_media_artifact(path="relative.mp4")
    assert r.passed is False
    assert "path_absolute" in r.failures


def test_inspect_rejects_missing_file(tmp_path):
    from app.services.media_qc import inspect_media_artifact

    r = inspect_media_artifact(path=tmp_path / "does_not_exist.mp4")
    assert r.passed is False
    assert "file_exists" in r.failures


def test_inspect_rejects_zero_byte_file(tmp_path):
    from app.services.media_qc import inspect_media_artifact

    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    r = inspect_media_artifact(path=empty)
    assert r.passed is False
    assert "file_size_positive" in r.failures


@pytest.mark.skipif(
    not _HAS_FFPROBE,
    reason="ffprobe required to drive the container/stream failure branch",
)
def test_inspect_rejects_bogus_container(tmp_path):
    from app.services.media_qc import inspect_media_artifact

    bogus = tmp_path / "garbage.mp4"
    bogus.write_bytes(b"not really an mp4" * 100)
    r = inspect_media_artifact(path=bogus)
    assert r.passed is False
    assert "ffprobe_inspection" in r.failures


def test_inspect_checksum_mismatch_fails(tmp_path):
    """Even without ffprobe, the checksum check runs."""
    from app.services.media_qc import inspect_media_artifact

    f = tmp_path / "thing.mp4"
    f.write_bytes(b"hello world")
    r = inspect_media_artifact(
        path=f, expected_checksum_sha256="0" * 64
    )
    assert r.passed is False
    assert "checksum_match" in r.failures


def _make_tiny_mp4(out_path: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=blue:s=64x64:r=10:d=1",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=cl=mono:r=22050:d=1",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=30)


@pytest.mark.skipif(
    not (_HAS_FFMPEG and _HAS_FFPROBE),
    reason="ffmpeg + ffprobe required for happy-path inspect_media_artifact",
)
def test_inspect_real_tiny_mp4_passes(tmp_path):
    from app.services.media_qc import inspect_media_artifact

    mp4 = tmp_path / "tiny.mp4"
    _make_tiny_mp4(mp4)
    r = inspect_media_artifact(path=mp4, expected_duration_seconds=1.0)
    assert r.passed is True, r
    assert r.video_stream_present is True
    assert r.audio_stream_present is True
    assert r.duration_seconds is not None and 0.5 <= r.duration_seconds <= 2.0
    assert r.width == 64 and r.height == 64
    assert r.duration_delta_seconds is not None
    assert r.duration_delta_seconds < 1.0


@pytest.mark.skipif(
    not (_HAS_FFMPEG and _HAS_FFPROBE),
    reason="ffmpeg + ffprobe required for duration-delta path",
)
def test_inspect_duration_drift_warns(tmp_path):
    from app.services.media_qc import inspect_media_artifact

    mp4 = tmp_path / "tiny.mp4"
    _make_tiny_mp4(mp4)
    # 1s clip; expected 3s → delta=2s → warn (between 1s and 5s).
    r = inspect_media_artifact(path=mp4, expected_duration_seconds=3.0)
    assert r.passed is True
    assert "duration_drift" in r.warnings


@pytest.mark.skipif(
    not (_HAS_FFMPEG and _HAS_FFPROBE),
    reason="ffmpeg + ffprobe required for duration-fail threshold",
)
def test_inspect_duration_far_drift_fails(tmp_path):
    from app.services.media_qc import inspect_media_artifact

    mp4 = tmp_path / "tiny.mp4"
    _make_tiny_mp4(mp4)
    # 1s clip; expected 30s → delta=29s → fail (>= 5s).
    r = inspect_media_artifact(path=mp4, expected_duration_seconds=30.0)
    assert r.passed is False
    assert "duration_within_tolerance" in r.failures


@pytest.mark.skipif(
    not (_HAS_FFMPEG and _HAS_FFPROBE),
    reason="ffmpeg + ffprobe required for require_audio path",
)
def test_inspect_video_only_mp4_warns_or_fails_by_require_audio(tmp_path):
    from app.services.media_qc import inspect_media_artifact

    mp4 = tmp_path / "no_audio.mp4"
    # Video-only synthesis.
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x64:r=10:d=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(mp4),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    soft = inspect_media_artifact(path=mp4, require_audio=False)
    assert soft.passed is True
    assert "audio_stream_absent" in soft.warnings
    hard = inspect_media_artifact(path=mp4, require_audio=True)
    assert hard.passed is False
    assert "audio_stream_present" in hard.failures


def test_inspect_module_has_no_torch_at_load():
    code = (
        "import sys\n"
        "import app.services.media_qc  # noqa: F401\n"
        "print('torch' in sys.modules)\n"
    )
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=20,
        cwd=str(Path(__file__).resolve().parents[2]),
    )
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "False"


# ---------------------------------------------------------------------------
# /api/v1/qc/inspect endpoint
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def app_under_test(monkeypatch, tmp_path):
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    monkeypatch.setenv("UPLOAD_AUDIO_ROOT", str(tmp_path / "audio"))
    monkeypatch.setenv("UPLOAD_IMAGE_ROOT", str(tmp_path / "images"))
    monkeypatch.setenv("UPLOAD_TEXT_ROOT", str(tmp_path / "text"))
    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(artifacts_root))
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
        yield client, artifacts_root, tmp_path
    await fake.aclose()
    queue_publisher.reset_redis_client()
    await core_db.async_reset_engine()


async def _create_job(client: AsyncClient, *, duration: int = 30) -> str:
    r = await client.post(
        "/api/v1/jobs",
        json={
            "brief": "phase 8c",
            "synthetic_person_confirmed": True,
            "consent_confirmed": True,
            "target_duration_seconds": duration,
            "watermark_required": True,
            "c2pa_required": True,
            "script_text": "phase 8c",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _register_artifact(
    *,
    job_id: str,
    artifact_type: str,
    local_path: Path,
    mime_type: str = "video/mp4",
    checksum: str | None = None,
) -> str:
    from app.core.db import get_sessionmaker
    from app.services import artifact_service

    sm = get_sessionmaker()
    async with sm() as session:
        art = await artifact_service.register_artifact(
            session,
            job_id=uuid.UUID(job_id),
            artifact_type=artifact_type,
            uri=local_path.as_uri(),
            local_path=str(local_path),
            mime_type=mime_type,
            size_bytes=local_path.stat().st_size,
            checksum_sha256=checksum,
        )
        await session.commit()
        return str(art.id)


async def test_qc_inspect_unknown_job_returns_404(app_under_test):
    client, *_ = app_under_test
    r = await client.post(
        "/api/v1/qc/inspect", json={"job_id": str(uuid.uuid4())}
    )
    assert r.status_code == 404


async def test_qc_inspect_no_media_returns_missing(app_under_test):
    client, *_ = app_under_test
    job_id = await _create_job(client)
    r = await client.post("/api/v1/qc/inspect", json={"job_id": job_id})
    body = r.json()
    assert body["status"] == "missing_inputs"
    assert body["error_code"] == "media_artifact_missing"
    assert body["report"] is None


async def test_qc_inspect_wrong_artifact_type_rejected(app_under_test, tmp_path):
    """Pass an audio artifact id where a media artifact is expected."""
    client, artifacts_root, _ = app_under_test
    job_id = await _create_job(client)
    aud = artifacts_root / "audio.wav"
    aud.write_bytes(b"RIFF" + b"\x00" * 40)
    aud_id = await _register_artifact(
        job_id=job_id,
        artifact_type="audio",
        local_path=aud,
        mime_type="audio/wav",
    )
    r = await client.post(
        "/api/v1/qc/inspect", json={"job_id": job_id, "artifact_id": aud_id}
    )
    body = r.json()
    assert body["status"] == "missing_inputs"
    assert body["error_code"] == "wrong_artifact_type"


async def test_qc_inspect_outside_root_rejected(app_under_test, tmp_path):
    client, _, _ = app_under_test
    job_id = await _create_job(client)
    outside = tmp_path / "outside"
    outside.mkdir()
    bad = outside / "leak.mp4"
    bad.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 64)
    bad_id = await _register_artifact(
        job_id=job_id, artifact_type="video", local_path=bad
    )
    r = await client.post(
        "/api/v1/qc/inspect", json={"job_id": job_id, "artifact_id": bad_id}
    )
    body = r.json()
    assert body["status"] == "not_configured"
    assert body["error_code"] == "artifact_outside_allowed_roots"


@pytest.mark.skipif(
    not (_HAS_FFMPEG and _HAS_FFPROBE),
    reason="ffmpeg + ffprobe required for real-success qc inspect path",
)
async def test_qc_inspect_real_mp4_returns_populated_report(app_under_test):
    client, artifacts_root, _ = app_under_test
    job_id = await _create_job(client, duration=15)
    mp4 = artifacts_root / "video" / job_id / "real.mp4"
    mp4.parent.mkdir(parents=True, exist_ok=True)
    _make_tiny_mp4(mp4)
    vid_id = await _register_artifact(
        job_id=job_id, artifact_type="video", local_path=mp4
    )
    # Override expected_duration_seconds=1.0 to match the synthesised
    # 1-second MP4 — otherwise the job's 15s target drives a duration
    # warn/fail that's unrelated to what we're pinning here.
    r = await client.post(
        "/api/v1/qc/inspect",
        json={
            "job_id": job_id,
            "artifact_id": vid_id,
            "expected_duration_seconds": 1.0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "completed"
    report = body["report"]
    assert report["passed"] is True
    assert report["video_stream_present"] is True
    assert report["audio_stream_present"] is True
    assert report["width"] == 64 and report["height"] == 64
    # File-size + checks list populated.
    assert report["file_size_bytes"] > 0
    assert len(report["checks"]) >= 4


@pytest.mark.skipif(
    not (_HAS_FFMPEG and _HAS_FFPROBE),
    reason="ffmpeg + ffprobe required for prefer-final-export branch",
)
async def test_qc_inspect_prefers_final_export_over_video(app_under_test):
    """When both a video and a final_export artifact exist for the job,
    the auto-pick path selects the final_export (operators usually want
    to validate the packaged output)."""
    client, artifacts_root, _ = app_under_test
    job_id = await _create_job(client, duration=15)
    src = artifacts_root / "video" / job_id / "src.mp4"
    src.parent.mkdir(parents=True, exist_ok=True)
    _make_tiny_mp4(src)
    await _register_artifact(
        job_id=job_id, artifact_type="video", local_path=src
    )
    final = artifacts_root / "final_export" / job_id / "final.mp4"
    final.parent.mkdir(parents=True, exist_ok=True)
    _make_tiny_mp4(final)
    final_id = await _register_artifact(
        job_id=job_id, artifact_type="final_export", local_path=final
    )

    r = await client.post(
        "/api/v1/qc/inspect",
        json={"job_id": job_id, "expected_duration_seconds": 1.0},
    )
    body = r.json()
    assert body["status"] == "completed"
    assert body["artifact_id"] == final_id
    assert body["artifact_type"] == "final_export"


# ---------------------------------------------------------------------------
# Phase 3I metadata-only QC handler unchanged
# ---------------------------------------------------------------------------


def test_phase3i_qc_handler_still_metadata_only():
    """Sanity grep: Phase 8C is purely additive at the API layer; the
    Phase 3I DAG QC handler still describes itself as metadata-only.
    A future contributor reading this test sees that real-media QC
    lives in a new service, not inside the DAG handler."""
    src = (Path(__file__).resolve().parents[2] / "agents" / "qc" / "handler.py").read_text()
    assert "Phase 3I QC is metadata-only" in src or "Phase 3I" in src
    assert "No ffmpeg, no ffprobe" in src
