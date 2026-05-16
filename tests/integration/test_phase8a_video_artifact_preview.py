"""Phase 8A — video artifact preview + safe content serving.

What this phase tests:

- ``/api/v1/artifacts/{id}/content`` now serves ``artifact_type=video``
  with the recorded ``video/mp4`` mime type.
- Unknown artifact id → 404.
- Non-serveable artifact type (e.g. ``edit_plan``) → 415.
- ``local_path`` outside every allowed root → 403.
- ``local_path`` pointing at a missing file → 404.
- ``?download=true`` switches Content-Disposition to ``attachment`` and
  picks a safe ``artifact-<short-id>.mp4`` filename — never the raw
  on-disk path.
- The ``ARTIFACTS_LOCAL_ROOT`` env (the Phase 7D / 8B output area) is
  honoured as an allowed root.
- The ``video_inspection.inspect_video()`` helper:
   - returns ``available=False, reason="ffprobe_missing"`` when
     ffprobe isn't on PATH (skipped if it is);
   - returns ``available=False, reason="invalid_path"`` on a missing
     / relative / non-file path;
   - returns ``available=False, reason="ffprobe_failed"`` on a clearly
     bogus file (skipped if ffprobe isn't installed).
"""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# App fixture mirrors Phase 4F + adds an artifacts root that the video
# rows can live under.
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


def _write_fake_mp4(p: Path) -> int:
    """Write a sentinel MP4-shaped file. Returns the byte length."""
    # Minimal ftyp box + filler. Browsers won't decode it, but the
    # endpoint just streams whatever the artifact row points at.
    payload = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isomiso2mp41" + b"\x00" * 256
    p.write_bytes(payload)
    return len(payload)


async def _register_video_artifact(
    client: AsyncClient,
    *,
    local_path: Path,
) -> str:
    """Insert a video artifact row directly so we don't need the full
    Phase 7D real-inference path to test the content endpoint."""
    from app.core.db import get_sessionmaker
    from app.services import artifact_service

    sm = get_sessionmaker()
    async with sm() as session:
        art = await artifact_service.register_artifact(
            session,
            artifact_type="video",
            uri=local_path.as_uri(),
            local_path=str(local_path),
            mime_type="video/mp4",
            size_bytes=local_path.stat().st_size,
            duration_seconds=3.5,
            width=512,
            height=512,
            checksum_sha256="deadbeef" * 8,
        )
        await session.commit()
        return str(art.id)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_video_artifact_content_returns_video_mp4(app_under_test):
    client, artifacts_root, _ = app_under_test
    out = artifacts_root / "video" / "job-x" / "out.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    size = _write_fake_mp4(out)

    artifact_id = await _register_video_artifact(client, local_path=out)
    r = await client.get(f"/api/v1/artifacts/{artifact_id}/content")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("video/mp4")
    # Default (no ?download) → inline.
    assert r.headers["content-disposition"].lower().startswith("inline")
    assert len(r.content) == size


async def test_video_artifact_content_supports_download_param(app_under_test):
    client, artifacts_root, _ = app_under_test
    out = artifacts_root / "video" / "dl-test" / "out.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    _write_fake_mp4(out)

    artifact_id = await _register_video_artifact(client, local_path=out)
    r = await client.get(f"/api/v1/artifacts/{artifact_id}/content?download=true")
    assert r.status_code == 200, r.text
    disposition = r.headers["content-disposition"].lower()
    assert disposition.startswith("attachment")
    # Filename must not leak the raw local path.
    assert str(out) not in r.headers["content-disposition"]
    # Filename must end in .mp4 (Phase 8A mime → suffix map).
    assert ".mp4" in r.headers["content-disposition"]


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


async def test_unknown_artifact_returns_404(app_under_test):
    client, *_ = app_under_test
    r = await client.get(f"/api/v1/artifacts/{uuid.uuid4()}/content")
    assert r.status_code == 404


async def test_video_artifact_missing_file_returns_404(app_under_test):
    client, artifacts_root, _ = app_under_test
    out = artifacts_root / "video" / "missing" / "vanished.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    _write_fake_mp4(out)
    artifact_id = await _register_video_artifact(client, local_path=out)
    # Now remove the file on disk; the DB row still points at it.
    out.unlink()
    r = await client.get(f"/api/v1/artifacts/{artifact_id}/content")
    assert r.status_code == 404


async def test_video_artifact_outside_allowed_roots_returns_403(
    app_under_test, tmp_path
):
    """A video registered with a local_path outside ARTIFACTS_LOCAL_ROOT
    and the upload roots must be refused with 403 — the on-disk file
    can exist, but the endpoint must refuse to serve it."""
    client, _, _ = app_under_test
    outside = tmp_path / "outside_root"
    outside.mkdir()
    bad = outside / "leaked.mp4"
    _write_fake_mp4(bad)

    from app.core.db import get_sessionmaker
    from app.services import artifact_service

    sm = get_sessionmaker()
    async with sm() as session:
        art = await artifact_service.register_artifact(
            session,
            artifact_type="video",
            uri=bad.as_uri(),
            local_path=str(bad),
            mime_type="video/mp4",
        )
        await session.commit()
        artifact_id = art.id

    r = await client.get(f"/api/v1/artifacts/{artifact_id}/content")
    assert r.status_code == 403


async def test_path_traversal_rejected_before_resolve(app_under_test):
    """A local_path with explicit ``..`` segments must be refused
    without touching the filesystem (defence-in-depth)."""
    client, *_ = app_under_test
    from app.core.db import get_sessionmaker
    from app.services import artifact_service

    sm = get_sessionmaker()
    async with sm() as session:
        art = await artifact_service.register_artifact(
            session,
            artifact_type="video",
            uri="file:///tmp/../etc/passwd",
            local_path="/tmp/../etc/passwd",
            mime_type="video/mp4",
        )
        await session.commit()
        artifact_id = art.id
    r = await client.get(f"/api/v1/artifacts/{artifact_id}/content")
    assert r.status_code == 403


async def test_non_serveable_type_unchanged(app_under_test):
    """Phase 4F invariant: non-serveable types still return 415."""
    client, *_ = app_under_test
    from app.core.db import get_sessionmaker
    from app.services import artifact_service

    sm = get_sessionmaker()
    async with sm() as session:
        art = await artifact_service.register_artifact(
            session,
            artifact_type="edit_plan",
            uri="file:///tmp/plan.json",
            local_path="/tmp/plan.json",
            mime_type="application/json",
        )
        await session.commit()
        artifact_id = art.id
    r = await client.get(f"/api/v1/artifacts/{artifact_id}/content")
    assert r.status_code == 415


# ---------------------------------------------------------------------------
# Video inspection helper — never raises, returns categorised reasons
# ---------------------------------------------------------------------------


def test_inspect_video_returns_invalid_path_for_relative_path():
    from app.services.video_inspection import inspect_video

    info = inspect_video("relative/not_absolute.mp4")
    assert info.available is False
    assert info.reason == "invalid_path"


def test_inspect_video_returns_invalid_path_for_missing_file(tmp_path):
    from app.services.video_inspection import inspect_video

    info = inspect_video(tmp_path / "does_not_exist.mp4")
    assert info.available is False
    assert info.reason == "invalid_path"


@pytest.mark.skipif(
    shutil.which("ffprobe") is None,
    reason="ffprobe not installed; this branch needs the binary on PATH",
)
def test_inspect_video_categorises_invalid_container(tmp_path):
    from app.services.video_inspection import inspect_video

    bogus = tmp_path / "totally_not_an_mp4.mp4"
    bogus.write_bytes(b"this is not a video file" * 10)
    info = inspect_video(bogus)
    assert info.available is False
    # Either ``ffprobe_failed`` (most likely) or ``parse_failed``; both
    # are acceptable categorised non-crashes.
    assert info.reason in ("ffprobe_failed", "parse_failed")


def test_inspect_video_returns_ffprobe_missing_when_binary_absent(monkeypatch, tmp_path):
    """Even if ffprobe is on the operator's PATH, hide it via the
    helper's ``shutil.which`` check to drive the missing branch."""
    from app.services import video_inspection

    monkeypatch.setattr(video_inspection, "has_ffprobe", lambda: False)
    info = video_inspection.inspect_video(tmp_path / "anything.mp4")
    assert info.available is False
    assert info.reason == "ffprobe_missing"


# ---------------------------------------------------------------------------
# Module-load safety — no torch / no heavy ML deps
# ---------------------------------------------------------------------------


def test_video_inspection_module_has_no_torch_at_load():
    import subprocess
    import sys

    code = (
        "import sys\n"
        "import app.services.video_inspection  # noqa: F401\n"
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
