"""Phase 9D — editor stops emitting fake ``reel_draft.mp4``.

Three branches under test:

1. No real upstream video → metadata-only placeholder reel_draft
   (``placeholder://`` URI, ``real_editor_output=False``,
   ``editor_mode="metadata_only"``, ``reason="no_real_video_artifact"``).
2. Real upstream video + ffmpeg on PATH → editor remuxes via subprocess
   and emits a real ``ArtifactRef`` with ``local_path`` / checksum /
   size / mime ``video/mp4``.
3. Real upstream video but ffmpeg missing → ``StageRejection`` with
   code ``editor_ffmpeg_missing``; no phantom artifact written.

Plus: partial-output cleanup on failure, and QC happily accepts both
real and metadata-only reel_drafts (each with the right pass/warn
shape).
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_HAS_FFMPEG = shutil.which("ffmpeg") is not None


def _build_state_with_lipsync(
    *,
    talking_head_ref,
    target: int = 30,
):
    from common.schemas import ArtifactRef, DagState, StageOutput

    job_id = uuid.uuid4()
    state = DagState(
        job_id=job_id,
        brief="phase 9d editor smoke",
        target_duration_seconds=target,
        synthetic_person_confirmed=True,
        consent_confirmed=True,
        watermark_required=True,
        c2pa_required=True,
    )
    state.stage_outputs["lipsync"] = StageOutput(
        artifacts={"talking_head": talking_head_ref}
    )
    structured = {
        "hook": "hook",
        "body": "body",
        "cta": "cta",
        "full_script": "hook body cta",
        "estimated_duration_seconds": float(target),
        "language": "en",
        "provider": "template",
        "model": "template-v1",
        "prompt_version": "v1",
        "metadata": {},
    }
    state.stage_outputs["scriptwriter"] = StageOutput(
        artifacts={
            "script": ArtifactRef(
                artifact_type="script",
                uri=f"s3://bucket/{job_id}/script.json",
                mime_type="application/json",
                checksum_sha256="a" * 64,
                size_bytes=42,
                extra={"structured_script": structured},
            )
        }
    )
    return state


def _make_real_mp4(path: Path) -> None:
    """Write a tiny, real MP4 using ffmpeg from a lavfi-generated test
    pattern. One second of 64x64 video, no audio, fast settings."""
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=red:s=64x64:d=1",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, timeout=30, check=False)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")[-500:]
    assert path.is_file() and path.stat().st_size > 0


def _sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Branch 1 — no real upstream video → metadata-only placeholder.
# ---------------------------------------------------------------------------


async def test_no_upstream_video_emits_metadata_only_placeholder():
    from agents.editor.handler import run as editor_run
    from common.schemas import ArtifactRef

    talking_head = ArtifactRef(
        artifact_type="video",
        uri=f"s3://bucket/{uuid.uuid4()}/talking_head.mp4",
        # No local_path, no checksum — this is the typical Phase 2/3 stub.
    )
    state = _build_state_with_lipsync(talking_head_ref=talking_head)
    out = await editor_run(state)

    reel = out.artifacts["reel_draft"]
    assert reel.uri.startswith("placeholder://")
    assert not reel.uri.endswith(".mp4")
    assert reel.local_path is None
    assert reel.checksum_sha256 is None
    assert reel.size_bytes is None
    extra = reel.extra
    assert extra["real_editor_output"] is False
    assert extra["editor_mode"] == "metadata_only"
    assert extra["reason"] == "no_real_video_artifact"
    assert extra["is_placeholder"] is True


async def test_upstream_video_with_local_path_but_no_checksum_treated_as_placeholder():
    """Defence-in-depth: a local_path alone (without a checksum) is not
    enough to count as a real upstream video — we need both signals."""
    from agents.editor.handler import run as editor_run
    from common.schemas import ArtifactRef

    talking_head = ArtifactRef(
        artifact_type="video",
        uri="file:///tmp/fake.mp4",
        local_path="/tmp/this_does_not_exist.mp4",
        # checksum_sha256 missing
    )
    state = _build_state_with_lipsync(talking_head_ref=talking_head)
    out = await editor_run(state)
    reel = out.artifacts["reel_draft"]
    assert reel.extra["real_editor_output"] is False
    assert reel.extra["editor_mode"] == "metadata_only"


async def test_upstream_video_with_missing_file_falls_back_to_placeholder(tmp_path):
    """If checksum+local_path are set but the file isn't on disk, the
    editor must NOT call ffmpeg — it falls back to metadata-only."""
    from agents.editor.handler import run as editor_run
    from common.schemas import ArtifactRef

    missing = tmp_path / "vanished.mp4"  # never created
    talking_head = ArtifactRef(
        artifact_type="video",
        uri=missing.as_uri(),
        local_path=str(missing),
        checksum_sha256="b" * 64,
        mime_type="video/mp4",
    )
    state = _build_state_with_lipsync(talking_head_ref=talking_head)
    out = await editor_run(state)
    reel = out.artifacts["reel_draft"]
    assert reel.extra["real_editor_output"] is False


# ---------------------------------------------------------------------------
# Branch 2 — real upstream MP4 → ffmpeg remux → real reel_draft.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg is required for the real-remux path")
async def test_real_upstream_video_produces_real_reel_draft(tmp_path, monkeypatch):
    from agents.editor.handler import run as editor_run
    from common.schemas import ArtifactRef

    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path / "artifacts"))

    src_path = tmp_path / "upstream_talking_head.mp4"
    _make_real_mp4(src_path)
    src_checksum = _sha256_of(src_path)
    talking_head = ArtifactRef(
        artifact_type="video",
        uri=src_path.as_uri(),
        local_path=str(src_path),
        checksum_sha256=src_checksum,
        size_bytes=src_path.stat().st_size,
        mime_type="video/mp4",
        duration_seconds=1.0,
        width=64,
        height=64,
        extra={"phase": "phase7d_real_inference"},
    )
    state = _build_state_with_lipsync(talking_head_ref=talking_head)
    out = await editor_run(state)

    reel = out.artifacts["reel_draft"]
    assert reel.local_path
    assert Path(reel.local_path).is_file()
    assert Path(reel.local_path).stat().st_size > 0
    assert reel.checksum_sha256 and len(reel.checksum_sha256) == 64
    assert reel.size_bytes == Path(reel.local_path).stat().st_size
    assert reel.mime_type == "video/mp4"
    # Output lives under ARTIFACTS_LOCAL_ROOT/video/{job_id}/...
    expected_dir = Path(tmp_path / "artifacts" / "video" / str(state.job_id))
    assert Path(reel.local_path).parent == expected_dir
    extra = reel.extra
    assert extra["real_editor_output"] is True
    assert extra["editor_mode"] == "ffmpeg_remux"
    assert extra["input_video_uri"] == src_path.as_uri()
    assert extra["input_video_checksum"] == src_checksum
    # The remuxed output is a distinct file with its own checksum.
    assert reel.checksum_sha256 != src_checksum or reel.local_path != str(src_path)


# ---------------------------------------------------------------------------
# Branch 3 — ffmpeg missing → StageRejection, no phantom output.
# ---------------------------------------------------------------------------


async def test_ffmpeg_missing_raises_clean_rejection(tmp_path, monkeypatch):
    from agents.editor import handler as editor_module
    from common.exceptions import StageRejection
    from common.schemas import ArtifactRef

    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path / "artifacts"))

    # Make a "real" upstream by writing a non-empty file and computing
    # its sha — we'll never actually shell out because ffmpeg is patched
    # to None.
    src_path = tmp_path / "upstream.mp4"
    src_path.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 100)
    talking_head = ArtifactRef(
        artifact_type="video",
        uri=src_path.as_uri(),
        local_path=str(src_path),
        checksum_sha256=_sha256_of(src_path),
        size_bytes=src_path.stat().st_size,
        mime_type="video/mp4",
    )
    state = _build_state_with_lipsync(talking_head_ref=talking_head)

    monkeypatch.setattr(editor_module.shutil, "which", lambda _name: None)

    with pytest.raises(StageRejection) as ei:
        await editor_module.run(state)
    assert "editor_ffmpeg_missing" in str(ei.value)
    # No reel_draft file should have been written.
    out_dir = Path(tmp_path / "artifacts" / "video" / str(state.job_id))
    leftover = list(out_dir.glob("reel_draft_*.mp4")) if out_dir.is_dir() else []
    assert leftover == []


# ---------------------------------------------------------------------------
# Branch 4 — ffmpeg returns non-zero → partial output cleaned, rejection.
# ---------------------------------------------------------------------------


async def test_ffmpeg_failure_cleans_partial_output_and_rejects(tmp_path, monkeypatch):
    from agents.editor import handler as editor_module
    from common.exceptions import StageRejection
    from common.schemas import ArtifactRef

    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path / "artifacts"))
    src_path = tmp_path / "upstream.mp4"
    src_path.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 100)
    talking_head = ArtifactRef(
        artifact_type="video",
        uri=src_path.as_uri(),
        local_path=str(src_path),
        checksum_sha256=_sha256_of(src_path),
        size_bytes=src_path.stat().st_size,
        mime_type="video/mp4",
    )
    state = _build_state_with_lipsync(talking_head_ref=talking_head)

    # Fake ffmpeg: write a partial file then return non-zero.
    class _FakeCompleted:
        def __init__(self, stderr: bytes, returncode: int) -> None:
            self.stderr = stderr
            self.returncode = returncode

    def _fake_run(cmd, capture_output, timeout, check):
        out = Path(cmd[cmd.index("-c") + 2])  # arg after "-c", "copy"
        # cmd is ["ffmpeg","-y","-i", <src>, "-c", "copy", <dst>]
        dst = Path(cmd[-1])
        dst.write_bytes(b"partial")
        return _FakeCompleted(b"contrived failure", 1)

    monkeypatch.setattr(editor_module.subprocess, "run", _fake_run)
    monkeypatch.setattr(editor_module.shutil, "which", lambda _name: "/usr/bin/ffmpeg")

    with pytest.raises(StageRejection) as ei:
        await editor_module.run(state)
    assert "editor_ffmpeg_failed" in str(ei.value)
    # Partial output must have been cleaned.
    out_dir = Path(tmp_path / "artifacts" / "video" / str(state.job_id))
    leftover = list(out_dir.glob("reel_draft_*.mp4"))
    assert leftover == [], leftover


# ---------------------------------------------------------------------------
# QC happily inspects both real and placeholder reel_drafts.
# ---------------------------------------------------------------------------


async def test_qc_accepts_metadata_only_reel_draft_as_passing():
    from agents.editor.handler import run as editor_run
    from agents.qc.handler import run as qc_run
    from common.schemas import ArtifactRef

    talking_head = ArtifactRef(artifact_type="video", uri="s3://bucket/x/talking_head.mp4")
    state = _build_state_with_lipsync(talking_head_ref=talking_head)
    editor_out = await editor_run(state)
    state.stage_outputs["editor"] = editor_out

    qc_out = await qc_run(state)
    qc_ref = qc_out.artifacts["qc_report"]
    report = qc_ref.extra["qc_report"]
    by_name = {c["name"]: c for c in report["checks"]}
    assert by_name["reel_draft_is_stub"]["decision"] == "pass"
    assert "metadata-only placeholder" in by_name["reel_draft_is_stub"]["detail"]
    assert qc_ref.extra["qc_passed"] is True


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg required")
async def test_qc_accepts_real_reel_draft_as_passing(tmp_path, monkeypatch):
    from agents.editor.handler import run as editor_run
    from agents.qc.handler import run as qc_run
    from common.schemas import ArtifactRef

    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path / "artifacts"))
    src_path = tmp_path / "src.mp4"
    _make_real_mp4(src_path)
    talking_head = ArtifactRef(
        artifact_type="video",
        uri=src_path.as_uri(),
        local_path=str(src_path),
        checksum_sha256=_sha256_of(src_path),
        size_bytes=src_path.stat().st_size,
        mime_type="video/mp4",
    )
    state = _build_state_with_lipsync(talking_head_ref=talking_head)
    editor_out = await editor_run(state)
    state.stage_outputs["editor"] = editor_out

    qc_out = await qc_run(state)
    qc_ref = qc_out.artifacts["qc_report"]
    report = qc_ref.extra["qc_report"]
    by_name = {c["name"]: c for c in report["checks"]}
    assert by_name["reel_draft_is_stub"]["decision"] == "pass"
    assert "real editor output" in by_name["reel_draft_is_stub"]["detail"]


# ---------------------------------------------------------------------------
# Publisher: must not claim a real final MP4 when upstream is placeholder.
# ---------------------------------------------------------------------------


async def test_publisher_never_emits_real_final_when_upstream_placeholder():
    from agents.editor.handler import run as editor_run
    from agents.publisher.handler import run as publisher_run
    from agents.qc.handler import run as qc_run
    from common.schemas import ArtifactRef, StageOutput

    talking_head = ArtifactRef(artifact_type="video", uri="s3://bucket/x/talking_head.mp4")
    state = _build_state_with_lipsync(talking_head_ref=talking_head)
    state.stage_outputs["editor"] = await editor_run(state)
    state.stage_outputs["qc"] = await qc_run(state)
    state.stage_outputs["export_disclosure_validation"] = StageOutput(
        artifacts={}, notes="ok"
    )

    pub_out = await publisher_run(state)
    reel_final = pub_out.artifacts["reel_final"]
    final_export = pub_out.artifacts["final_export"]
    assert reel_final.uri.startswith("placeholder://")
    assert not reel_final.uri.endswith(".mp4")
    assert reel_final.extra["real_final_export"] is False
    assert reel_final.extra["is_placeholder"] is True
    # The disclosure_status stays pending — Phase 3J invariant.
    assert final_export.extra["disclosure_status"] == "pending"


_ = pytest  # placate lint
