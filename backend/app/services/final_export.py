"""Phase 8B — real ffmpeg final-export service.

Takes a source video artifact, runs a controlled ffmpeg remux into the
artifacts root, and returns a result dict the API layer can register as
an ``ArtifactType.final_export`` row.

Safety contract:

- ``subprocess.run`` is always called with an argv ``list`` (never a
  shell string) and a finite ``timeout``.
- Source and output paths must be absolute, resolved, on-disk files.
- The output path is chosen by the caller (the API picks
  ``ARTIFACTS_LOCAL_ROOT/final_export/<job_id>/...``) — operators
  never control it directly.
- On any failure the partial output is unlinked before the failure
  dict is returned. No phantom files survive.
- ffprobe runs after the export to validate the output exists, has
  non-zero size, has a video stream, and to extract authoritative
  duration / dimensions for the artifact row.

Phase 8B does **not** burn-in a watermark, sign with C2PA, or upload
externally. The result dict carries
``disclosure_status="pending"`` + ``watermark_status="pending"`` +
``c2pa_status="pending"`` so downstream surfaces know real disclosure
work is still pending.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.video_inspection import inspect_video


# Finite wall clock for ffmpeg remux. A typical ``-c copy`` remux of a
# 60-second MP4 finishes in <1s; we set a generous cap so a slow CI
# host doesn't false-fail, but bounded so a pathological input doesn't
# hang the handler indefinitely.
_FFMPEG_TIMEOUT_SECONDS = 300


@dataclass(frozen=True)
class FinalExportResult:
    """Return shape from ``finalize_video()``.

    On success (``status="completed"``), the fields on the right of
    ``status`` are all populated. On any failure mode, only
    ``status`` + ``error_code`` + ``message`` are guaranteed.
    """

    status: str  # "completed" | "ffmpeg_missing" | "ffprobe_missing" |
                 # "source_missing" | "source_invalid" | "export_failed" |
                 # "export_invalid"
    error_code: str | None = None
    message: str = ""
    output_path: str | None = None
    size_bytes: int | None = None
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    checksum_sha256: str | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    video_stream_present: bool = False
    audio_stream_present: bool = False
    container_format: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "error_code": self.error_code,
            "message": self.message,
            "output_path": self.output_path,
            "size_bytes": self.size_bytes,
            "duration_seconds": self.duration_seconds,
            "width": self.width,
            "height": self.height,
            "checksum_sha256": self.checksum_sha256,
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
            "video_stream_present": self.video_stream_present,
            "audio_stream_present": self.audio_stream_present,
            "container_format": self.container_format,
        }


def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def finalize_video(
    *,
    source_path: Path | str,
    output_dir: Path | str,
    audio_path: Path | str | None = None,
) -> FinalExportResult:
    """Remux ``source_path`` into a clean MP4 under ``output_dir``.

    - If ``audio_path`` is None: copy the source's existing audio /
      video streams ``-c copy`` (no re-encode, very fast).
    - If ``audio_path`` is provided: copy the video stream from
      ``source_path`` and replace the audio stream with ``audio_path``.
      Useful when SadTalker output drift made the embedded audio
      inaccurate.

    Refuses every unsafe input mode without launching ffmpeg.
    """
    if not has_ffmpeg():
        return FinalExportResult(
            status="ffmpeg_missing",
            error_code="ffmpeg_missing",
            message=(
                "ffmpeg is not on PATH in this image. The default light "
                "backend already installs ffmpeg (Phase 4F); rebuild if "
                "this fires."
            ),
        )

    src = Path(source_path)
    if not src.is_absolute():
        return FinalExportResult(
            status="source_invalid",
            error_code="source_invalid",
            message="source_path must be absolute",
        )
    if not src.is_file():
        return FinalExportResult(
            status="source_missing",
            error_code="source_missing",
            message=f"source video not on disk: {src}",
        )

    aud: Path | None = None
    if audio_path is not None:
        aud = Path(audio_path)
        if not aud.is_absolute():
            return FinalExportResult(
                status="source_invalid",
                error_code="source_invalid",
                message="audio_path must be absolute",
            )
        if not aud.is_file():
            return FinalExportResult(
                status="source_missing",
                error_code="source_missing",
                message=f"audio source not on disk: {aud}",
            )

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"final_{uuid.uuid4().hex}.mp4"

    # Build ffmpeg argv. ``-y`` (overwrite) is safe because we own the
    # output path (uuid-derived above). ``-c copy`` is the cheap remux
    # path; when audio is being replaced, we re-multiplex into MP4 with
    # ``-c:v copy -c:a aac``.
    cmd: list[str]
    if aud is None:
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    else:
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-i",
            str(aud),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_path),
        ]

    try:
        proc = subprocess.run(  # noqa: S603 — argv list, no shell.
            cmd,
            capture_output=True,
            text=True,
            timeout=_FFMPEG_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        _cleanup(output_path)
        return FinalExportResult(
            status="export_failed",
            error_code="export_failed",
            message=f"ffmpeg exceeded timeout of {_FFMPEG_TIMEOUT_SECONDS}s",
        )
    except FileNotFoundError:
        _cleanup(output_path)
        return FinalExportResult(
            status="ffmpeg_missing",
            error_code="ffmpeg_missing",
            message="ffmpeg disappeared between has_ffmpeg() check and spawn",
        )
    except OSError as exc:
        _cleanup(output_path)
        return FinalExportResult(
            status="export_failed",
            error_code="export_failed",
            message=f"ffmpeg spawn_failed: {type(exc).__name__}",
        )

    if proc.returncode != 0:
        _cleanup(output_path)
        # Surface only the last short line of stderr — never the full
        # transcript, which can contain operator paths.
        stderr_tail = (proc.stderr or "").strip().splitlines()
        tail = stderr_tail[-1] if stderr_tail else "(no stderr)"
        return FinalExportResult(
            status="export_failed",
            error_code="export_failed",
            message=f"ffmpeg returned non-zero ({proc.returncode}): {tail[:160]}",
        )

    # Validate the output exists and has bytes.
    if not output_path.is_file() or output_path.stat().st_size == 0:
        _cleanup(output_path)
        return FinalExportResult(
            status="export_invalid",
            error_code="export_invalid",
            message="ffmpeg returned 0 but output is missing or empty",
        )

    # Inspect with ffprobe for authoritative metadata. If ffprobe is
    # absent we still keep the output, but populate only the fields we
    # can compute ourselves.
    info = inspect_video(output_path)
    if not info.available:
        size = output_path.stat().st_size
        return FinalExportResult(
            status="completed",
            output_path=str(output_path),
            size_bytes=size,
            checksum_sha256=_sha256_of_file(output_path),
            message=(
                f"ffmpeg succeeded but ffprobe inspection failed: "
                f"{info.reason}. Output kept; metadata limited."
            ),
        )
    if not info.video_stream_present:
        _cleanup(output_path)
        return FinalExportResult(
            status="export_invalid",
            error_code="export_invalid",
            message="ffmpeg output has no video stream",
        )

    checksum = _sha256_of_file(output_path)
    return FinalExportResult(
        status="completed",
        output_path=str(output_path),
        size_bytes=info.size_bytes,
        duration_seconds=info.duration_seconds,
        width=info.width,
        height=info.height,
        checksum_sha256=checksum,
        video_codec=info.video_codec,
        audio_codec=info.audio_codec,
        video_stream_present=info.video_stream_present,
        audio_stream_present=info.audio_stream_present,
        container_format=info.container_format,
    )


def _cleanup(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:  # pragma: no cover — defensive
        pass
