"""ffmpeg-backed audio conversion (Phase 4F).

The Phase 4A-2 audio upload only accepted WAV. Phase 4F broadens to
MP3 / M4A / AAC / FLAC / OGG. We keep WAV as the canonical pipeline
format — anything else is transcoded to PCM WAV by ffmpeg before the
existing Phase 3D validator runs.

ffmpeg is an **optional** runtime dependency. If it's not on PATH, the
upload still succeeds (the original file is stored + an artifact row
registered with a ``needs_conversion`` flag) but the operator sees a
clear warning. The light Docker image installs ffmpeg via apt-get so
the happy path works there.

This module deliberately does NOT touch video. ffmpeg is bounded to
audio decode + WAV mux.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


_FFMPEG_TIMEOUT_SECONDS = 60
_FFPROBE_TIMEOUT_SECONDS = 15


def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


@dataclass(frozen=True)
class ConvertedAudio:
    output_path: Path
    duration_seconds: float
    sample_rate: int
    channels: int
    size_bytes: int


class AudioConversionError(RuntimeError):
    pass


def probe_audio_duration(src: Path) -> float | None:
    """Return duration in seconds via ffprobe, or None if unavailable."""
    if not has_ffmpeg():
        return None
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(src),
        ]
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=_FFPROBE_TIMEOUT_SECONDS,
        )
        payload = json.loads(result.stdout)
        return float(payload.get("format", {}).get("duration", 0.0)) or None
    except Exception:
        return None


def convert_to_wav(
    src: Path,
    dst: Path,
    *,
    sample_rate: int = 22050,
    channels: int = 1,
) -> ConvertedAudio:
    """Run ``ffmpeg`` to produce a PCM WAV at the configured rate/channels.

    Raises :class:`AudioConversionError` if ffmpeg is unavailable or
    fails. The caller is responsible for cleaning up partial output files
    on error — we make a best-effort unlink before re-raising.
    """
    if not has_ffmpeg():
        raise AudioConversionError("audio_conversion_tool_missing")
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(src),
        "-vn",
        "-ac",
        str(channels),
        "-ar",
        str(sample_rate),
        "-acodec",
        "pcm_s16le",
        str(dst),
    ]
    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=_FFMPEG_TIMEOUT_SECONDS,
        )
    except subprocess.CalledProcessError as exc:
        dst.unlink(missing_ok=True)
        raise AudioConversionError(
            f"ffmpeg failed: {exc.stderr.strip() or exc.stdout.strip() or 'unknown error'}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        dst.unlink(missing_ok=True)
        raise AudioConversionError(
            f"ffmpeg timed out after {_FFMPEG_TIMEOUT_SECONDS}s"
        ) from exc
    duration = probe_audio_duration(dst) or 0.0
    size = dst.stat().st_size
    return ConvertedAudio(
        output_path=dst,
        duration_seconds=duration,
        sample_rate=sample_rate,
        channels=channels,
        size_bytes=size,
    )
