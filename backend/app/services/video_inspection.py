"""Bounded video metadata inspection via ffprobe.

Phase 8A — used by the artifact-content surface (and by Phase 8B's
final-export service, Phase 8C's media QC) to inspect a video file
without running any ML model.

Safety contract:

- ``subprocess.run`` is always called with an argv ``list`` (never a
  shell string) and a finite ``timeout``.
- The input path must be an absolute, resolved ``Path``. The helper
  refuses unresolved / relative / non-existent / non-file paths.
- ffprobe's stdout is parsed as JSON; any parse error → metadata
  unavailable (the caller's contract).
- If ffprobe is not on PATH, the helper returns ``available=False``
  and a clear reason; it never raises.

This module imports nothing heavy — no torch, no diffusers. It is
safe to import from the default light backend.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Hard upper bound on ffprobe runtime. ffprobe on a 60-second MP4 is
# typically <100 ms; we set a generous wall clock so a slow CI host
# doesn't false-fail. Anything close to this cap implies the input is
# pathological and we'd rather time out than block the request handler.
_FFPROBE_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class VideoMetadata:
    """Result envelope from ``inspect_video()``.

    ``available=True`` only when ffprobe ran cleanly and produced
    parsable JSON. Any failure mode populates ``reason`` instead.
    """

    available: bool
    reason: str = ""
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    video_stream_present: bool = False
    audio_stream_present: bool = False
    container_format: str | None = None
    size_bytes: int | None = None
    streams: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "reason": self.reason,
            "duration_seconds": self.duration_seconds,
            "width": self.width,
            "height": self.height,
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
            "video_stream_present": self.video_stream_present,
            "audio_stream_present": self.audio_stream_present,
            "container_format": self.container_format,
            "size_bytes": self.size_bytes,
        }


def has_ffprobe() -> bool:
    return shutil.which("ffprobe") is not None


def inspect_video(path: Path | str) -> VideoMetadata:
    """Inspect a video file. Never raises.

    Returns ``VideoMetadata(available=False, reason=...)`` for every
    non-success branch:

    - ``ffprobe_missing`` — ffprobe not on PATH (light backend image).
    - ``invalid_path`` — path is relative, doesn't exist, or isn't a file.
    - ``ffprobe_timeout`` — process exceeded the wall-clock budget.
    - ``ffprobe_failed`` — non-zero exit (corrupt file, unsupported
      container, etc.).
    - ``parse_failed`` — ffprobe output was not parseable JSON.

    The ``reason`` field is suitable for surfacing to operators; it
    does not echo internal paths.
    """
    if not has_ffprobe():
        return VideoMetadata(available=False, reason="ffprobe_missing")

    p = Path(path)
    if not p.is_absolute():
        return VideoMetadata(available=False, reason="invalid_path")
    if not p.exists() or not p.is_file():
        return VideoMetadata(available=False, reason="invalid_path")

    try:
        size_bytes = p.stat().st_size
    except OSError:
        return VideoMetadata(available=False, reason="invalid_path")

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(p),
    ]
    try:
        proc = subprocess.run(  # noqa: S603 — argv list, no shell.
            cmd,
            capture_output=True,
            text=True,
            timeout=_FFPROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return VideoMetadata(
            available=False, reason="ffprobe_timeout", size_bytes=size_bytes
        )
    except FileNotFoundError:
        # ffprobe disappeared between has_ffprobe() and the spawn —
        # race on a transient PATH, treat as missing.
        return VideoMetadata(available=False, reason="ffprobe_missing")
    except OSError as exc:
        return VideoMetadata(
            available=False,
            reason=f"spawn_failed: {type(exc).__name__}",
            size_bytes=size_bytes,
        )

    if proc.returncode != 0:
        return VideoMetadata(
            available=False, reason="ffprobe_failed", size_bytes=size_bytes
        )

    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return VideoMetadata(
            available=False, reason="parse_failed", size_bytes=size_bytes
        )

    return _build_metadata(data, size_bytes=size_bytes)


def _build_metadata(data: dict[str, Any], *, size_bytes: int) -> VideoMetadata:
    fmt = data.get("format") or {}
    streams = list(data.get("streams") or [])
    duration: float | None = None
    if "duration" in fmt:
        try:
            duration = float(fmt["duration"])
        except (TypeError, ValueError):
            duration = None
    container = fmt.get("format_name")

    video_stream: dict[str, Any] | None = None
    audio_stream: dict[str, Any] | None = None
    for s in streams:
        kind = s.get("codec_type")
        if kind == "video" and video_stream is None:
            video_stream = s
        elif kind == "audio" and audio_stream is None:
            audio_stream = s

    width = height = None
    video_codec: str | None = None
    if video_stream is not None:
        video_codec = video_stream.get("codec_name")
        w = video_stream.get("width")
        h = video_stream.get("height")
        if isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0:
            width = w
            height = h
        # Fallback: duration on the video stream when format lacks it.
        if duration is None:
            try:
                duration = float(video_stream.get("duration", "nan"))
            except (TypeError, ValueError):
                pass

    audio_codec: str | None = None
    if audio_stream is not None:
        audio_codec = audio_stream.get("codec_name")

    return VideoMetadata(
        available=True,
        duration_seconds=duration if (duration is not None and duration > 0) else None,
        width=width,
        height=height,
        video_codec=video_codec,
        audio_codec=audio_codec,
        video_stream_present=video_stream is not None,
        audio_stream_present=audio_stream is not None,
        container_format=container,
        size_bytes=size_bytes,
        streams=streams,
    )
