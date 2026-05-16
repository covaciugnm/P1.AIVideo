"""Phase 8B — real ffmpeg final export.

Default-suite tests cover:

- Job validation (unknown job → 404).
- Source video selection (no video → ``video_artifact_missing``;
  explicit unknown id → ``video_artifact_not_found``; wrong type →
  ``wrong_video_artifact_type``).
- Path safety (no local_path / traversal / outside allowed roots).
- ``ffmpeg_missing`` short-circuit (monkey-patched).
- Real export success path (skipped unless ffmpeg + ffprobe present on
  PATH). Pins: real ``final_export`` artifact registered with
  ``mime_type=video/mp4``, real ``local_path``,
  ``disclosure_status="pending"`` + ``c2pa_status="pending"`` +
  ``watermark_status="pending"`` in metadata.
- Partial output cleanup when ffmpeg fails (force a non-zero exit).
- No phantom artifact registered on failure.
"""
from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient


_HAS_FFMPEG = shutil.which("ffmpeg") is not None
_HAS_FFPROBE = shutil.which("ffprobe") is not None


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


def _make_tiny_mp4_with_ffmpeg(out_path: Path) -> None:
    """Synthesise a 1-second silent MP4 via ffmpeg. Used only when
    ffmpeg is on PATH (the only branch where real export is testable)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
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


async def _create_job(client: AsyncClient) -> str:
    r = await client.post(
        "/api/v1/jobs",
        json={
            "brief": "phase 8b",
            "synthetic_person_confirmed": True,
            "consent_confirmed": True,
            "target_duration_seconds": 30,
            "watermark_required": True,
            "c2pa_required": True,
            "script_text": "phase 8b",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _register_video_for_job(
    client: AsyncClient, *, job_id: str, local_path: Path
) -> str:
    from app.core.db import get_sessionmaker
    from app.services import artifact_service

    sm = get_sessionmaker()
    async with sm() as session:
        art = await artifact_service.register_artifact(
            session,
            job_id=uuid.UUID(job_id),
            artifact_type="video",
            uri=local_path.as_uri(),
            local_path=str(local_path),
            mime_type="video/mp4",
            size_bytes=local_path.stat().st_size,
            duration_seconds=1.0,
            width=64,
            height=64,
        )
        await session.commit()
        return str(art.id)


# ---------------------------------------------------------------------------
# Job + input validation
# ---------------------------------------------------------------------------


async def test_finalize_unknown_job_returns_404(app_under_test):
    client, *_ = app_under_test
    r = await client.post(
        "/api/v1/export/finalize", json={"job_id": str(uuid.uuid4())}
    )
    assert r.status_code == 404


async def test_finalize_no_video_artifact_returns_video_missing(app_under_test):
    client, *_ = app_under_test
    job_id = await _create_job(client)
    r = await client.post("/api/v1/export/finalize", json={"job_id": job_id})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "missing_inputs"
    assert body["error_code"] == "video_artifact_missing"
    assert body["final_export_artifact_id"] is None


async def test_finalize_explicit_unknown_video_returns_not_found(app_under_test):
    client, *_ = app_under_test
    job_id = await _create_job(client)
    r = await client.post(
        "/api/v1/export/finalize",
        json={"job_id": job_id, "video_artifact_id": str(uuid.uuid4())},
    )
    body = r.json()
    assert body["error_code"] == "video_artifact_not_found"


async def test_finalize_wrong_artifact_type_rejected(app_under_test, tmp_path):
    """Pass an audio artifact id where the video id is expected."""
    client, artifacts_root, _ = app_under_test
    job_id = await _create_job(client)

    from app.core.db import get_sessionmaker
    from app.services import artifact_service

    aud_path = artifacts_root / "audio" / "voice.wav"
    aud_path.parent.mkdir(parents=True, exist_ok=True)
    aud_path.write_bytes(b"RIFF" + b"\x00" * 40)
    sm = get_sessionmaker()
    async with sm() as session:
        aud = await artifact_service.register_artifact(
            session,
            job_id=uuid.UUID(job_id),
            artifact_type="audio",
            uri=aud_path.as_uri(),
            local_path=str(aud_path),
            mime_type="audio/wav",
        )
        await session.commit()
        aud_id = str(aud.id)

    r = await client.post(
        "/api/v1/export/finalize",
        json={"job_id": job_id, "video_artifact_id": aud_id},
    )
    body = r.json()
    assert body["error_code"] == "wrong_video_artifact_type"


async def test_finalize_video_outside_allowed_root_rejected(
    app_under_test, tmp_path
):
    """A video registered with a local_path outside ARTIFACTS_LOCAL_ROOT
    must be refused; even if the file exists, the API won't pass it to
    ffmpeg."""
    client, _, _ = app_under_test
    job_id = await _create_job(client)

    outside = tmp_path / "outside"
    outside.mkdir()
    bad = outside / "leaked.mp4"
    bad.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 64)
    vid_id = await _register_video_for_job(client, job_id=job_id, local_path=bad)

    r = await client.post(
        "/api/v1/export/finalize",
        json={"job_id": job_id, "video_artifact_id": vid_id},
    )
    body = r.json()
    assert body["status"] == "not_configured"
    assert body["error_code"] == "source_outside_allowed_roots"


async def test_finalize_video_no_local_path_rejected(app_under_test):
    """A video artifact row with local_path=NULL must short-circuit
    before ffmpeg."""
    client, *_ = app_under_test
    job_id = await _create_job(client)

    from app.core.db import get_sessionmaker
    from app.services import artifact_service

    sm = get_sessionmaker()
    async with sm() as session:
        art = await artifact_service.register_artifact(
            session,
            job_id=uuid.UUID(job_id),
            artifact_type="video",
            uri="s3://stub/foo.mp4",
            local_path=None,
            mime_type="video/mp4",
        )
        await session.commit()
        art_id = str(art.id)

    r = await client.post(
        "/api/v1/export/finalize",
        json={"job_id": job_id, "video_artifact_id": art_id},
    )
    body = r.json()
    assert body["error_code"] == "video_artifact_no_local_path"


# ---------------------------------------------------------------------------
# ffmpeg-missing short-circuit (monkey-patched)
# ---------------------------------------------------------------------------


async def test_finalize_ffmpeg_missing_returns_clean_error(
    app_under_test, monkeypatch, tmp_path
):
    client, artifacts_root, _ = app_under_test
    job_id = await _create_job(client)
    # Use any file under the artifacts root — the source-path check
    # passes, the ffmpeg gate fires first.
    src = artifacts_root / "video" / "any.mp4"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"\x00" * 64)
    vid_id = await _register_video_for_job(client, job_id=job_id, local_path=src)

    from app.services import final_export as fe_mod

    monkeypatch.setattr(fe_mod, "has_ffmpeg", lambda: False)

    r = await client.post(
        "/api/v1/export/finalize",
        json={"job_id": job_id, "video_artifact_id": vid_id},
    )
    body = r.json()
    assert body["error_code"] == "ffmpeg_missing"
    assert body["final_export_artifact_id"] is None


# ---------------------------------------------------------------------------
# Partial-cleanup contract — ffmpeg returns non-zero
# ---------------------------------------------------------------------------


async def test_finalize_export_failed_leaves_no_phantom_artifact(
    app_under_test, monkeypatch, tmp_path
):
    """If ffmpeg returns non-zero, the final-export service cleans up
    the partial file and the API registers no artifact."""
    client, artifacts_root, _ = app_under_test
    job_id = await _create_job(client)
    src = artifacts_root / "video" / "src.mp4"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"not a real mp4" * 32)
    vid_id = await _register_video_for_job(client, job_id=job_id, local_path=src)

    # Force ffmpeg to fail by pointing it at a non-existent binary
    # *after* the has_ffmpeg() check (simulates a flaky PATH); the
    # service's subprocess.run will hit FileNotFoundError.
    from app.services import final_export as fe_mod

    monkeypatch.setattr(fe_mod, "has_ffmpeg", lambda: True)
    original_run = subprocess.run

    def fake_run(cmd, **kwargs):
        # Emulate ffmpeg returning rc=1 with a stderr message.
        class _R:
            returncode = 1
            stdout = ""
            stderr = "fake: invalid input"

        return _R()

    monkeypatch.setattr(fe_mod.subprocess, "run", fake_run)

    r = await client.post(
        "/api/v1/export/finalize",
        json={"job_id": job_id, "video_artifact_id": vid_id},
    )
    body = r.json()
    assert body["status"] == "failed"
    assert body["error_code"] == "export_failed"
    assert body["final_export_artifact_id"] is None
    # The service writes to artifacts_root/final_export/<job>/; the
    # cleanup should leave that dir empty (or at most contain partial
    # cleanup artifacts ffmpeg might write before exiting).
    final_dir = artifacts_root / "final_export" / job_id
    if final_dir.exists():
        leftover = [p for p in final_dir.iterdir() if p.is_file()]
        assert leftover == [], f"unexpected leftover files: {leftover}"

    # Confirm no final_export artifact row was registered.
    from app.core.db import get_sessionmaker
    from app.models.artifact import Artifact
    from sqlalchemy import select

    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(
            select(Artifact).where(
                Artifact.job_id == uuid.UUID(job_id),
                Artifact.artifact_type == "final_export",
            )
        )
        assert result.scalar_one_or_none() is None

    _ = original_run  # silence unused


# ---------------------------------------------------------------------------
# Real export success path — requires ffmpeg + ffprobe
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (_HAS_FFMPEG and _HAS_FFPROBE),
    reason="ffmpeg + ffprobe required for real-export success path",
)
async def test_finalize_real_export_registers_final_export_artifact(
    app_under_test, tmp_path
):
    client, artifacts_root, _ = app_under_test
    job_id = await _create_job(client)
    # Synthesise a real 1-second silent MP4 inside the artifacts root.
    src = artifacts_root / "video" / job_id / "source.mp4"
    _make_tiny_mp4_with_ffmpeg(src)
    vid_id = await _register_video_for_job(client, job_id=job_id, local_path=src)

    r = await client.post(
        "/api/v1/export/finalize",
        json={"job_id": job_id, "video_artifact_id": vid_id},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "completed", body
    assert body["final_export_artifact_id"] is not None
    assert body["size_bytes"] > 0
    assert body["checksum_sha256"]
    assert body["metadata"]["disclosure_status"] == "pending"
    assert body["metadata"]["c2pa_status"] == "pending"
    assert body["metadata"]["watermark_status"] == "pending"

    # The registered artifact must be servable via the Phase 8A content
    # endpoint (final_export is now in the allow-list).
    content_r = await client.get(
        f"/api/v1/artifacts/{body['final_export_artifact_id']}/content"
    )
    assert content_r.status_code == 200
    assert content_r.headers["content-type"].startswith("video/mp4")


@pytest.mark.skipif(
    not (_HAS_FFMPEG and _HAS_FFPROBE),
    reason="ffmpeg + ffprobe required for real-export success path",
)
async def test_finalize_real_export_can_be_downloaded(app_under_test):
    """Phase 8A's ?download=true flow works for real final_export
    artifacts."""
    client, artifacts_root, _ = app_under_test
    job_id = await _create_job(client)
    src = artifacts_root / "video" / job_id / "source.mp4"
    _make_tiny_mp4_with_ffmpeg(src)
    vid_id = await _register_video_for_job(client, job_id=job_id, local_path=src)

    r = await client.post(
        "/api/v1/export/finalize",
        json={"job_id": job_id, "video_artifact_id": vid_id},
    )
    artifact_id = r.json()["final_export_artifact_id"]
    dl = await client.get(
        f"/api/v1/artifacts/{artifact_id}/content?download=true"
    )
    assert dl.status_code == 200
    disposition = dl.headers["content-disposition"].lower()
    assert disposition.startswith("attachment")
    assert ".mp4" in disposition


# ---------------------------------------------------------------------------
# Module-load isolation — final_export must not pull heavy deps
# ---------------------------------------------------------------------------


def test_final_export_module_has_no_torch_at_load():
    import sys

    code = (
        "import sys\n"
        "import app.services.final_export  # noqa: F401\n"
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
# Phase 3J publisher manifest unchanged — Phase 8B is additive
# ---------------------------------------------------------------------------


def test_publisher_handler_module_unchanged_by_phase8b():
    """Phase 8B leaves Phase 3J's metadata-only publisher untouched.
    A simple grep confirms the publisher still describes itself as
    'metadata-only' so a future contributor doesn't mistakenly think
    Phase 8B promoted it."""
    src = (Path(__file__).resolve().parents[2] / "agents" / "publisher" / "handler.py").read_text()
    # The handler still uses ``manifest`` as the export artifact body —
    # not a real MP4. Phase 8B's real MP4 path is operator-triggered,
    # not DAG-triggered.
    assert "Phase 3J stays metadata-only" in src
