"""Stdlib-only WAV validation + inspection.

Used by:
- The voice handler when ``voice_mode="provided_audio"`` and the audio
  reference is a ``local_path``, to confirm the file is actually a
  readable PCM WAV before promoting it to an artifact.
- The artifact service when registering an audio artifact from a local
  file path.

Deliberately uses only ``wave`` + ``hashlib`` + ``pathlib`` — no ffmpeg,
no librosa, no soundfile. ``wave`` handles standard PCM WAVs which is
the only format the Phase 3D contract permits.
"""
from __future__ import annotations

import hashlib
import wave
from dataclasses import dataclass
from pathlib import Path


_ALLOWED_MIME_TYPES = frozenset({"audio/wav", "audio/x-wav"})


@dataclass(frozen=True)
class AudioMetadata:
    """Result of a successful ``validate_and_inspect_wav`` call."""

    path: Path
    size_bytes: int
    sample_rate: int
    channels: int
    sample_width_bytes: int
    n_frames: int
    duration_seconds: float
    checksum_sha256: str
    mime_type: str


def _compute_sha256(path: Path, *, chunk_size: int = 64 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_and_inspect_wav(
    path: str | Path,
    *,
    mime_type: str,
    max_size_bytes: int | None = None,
    allowed_sample_rates: list[int] | None = None,
    allowed_channels: list[int] | None = None,
) -> AudioMetadata:
    """Open, inspect, and checksum a WAV file.

    Raises ``ValueError`` (the exception Pydantic and our handlers expect)
    on any of:

    - File does not exist or is not a regular file.
    - ``mime_type`` is not in ``{"audio/wav", "audio/x-wav"}``.
    - File size exceeds ``max_size_bytes`` (if specified).
    - WAV header is unreadable (caught from ``wave.Error``).
    - Sample rate is not in ``allowed_sample_rates`` (if specified).
    - Channel count is not in ``allowed_channels`` (if specified).

    On success, returns ``AudioMetadata`` with the extracted fields and
    the SHA-256 of the file contents.
    """
    if mime_type not in _ALLOWED_MIME_TYPES:
        raise ValueError(
            f"mime_type must be one of {sorted(_ALLOWED_MIME_TYPES)}; got {mime_type!r}"
        )

    p = Path(path)
    if not p.exists():
        raise ValueError(f"audio file not found: {path!s}")
    if not p.is_file():
        raise ValueError(f"audio path is not a regular file: {path!s}")

    size = p.stat().st_size
    if max_size_bytes is not None and size > max_size_bytes:
        raise ValueError(
            f"audio file size {size} exceeds AUDIO_MAX_FILE_SIZE_BYTES "
            f"limit {max_size_bytes}"
        )

    try:
        with wave.open(str(p), "rb") as w:
            sample_rate = w.getframerate()
            channels = w.getnchannels()
            sample_width = w.getsampwidth()
            n_frames = w.getnframes()
    except wave.Error as exc:
        raise ValueError(f"invalid WAV header for {p.name}: {exc}") from exc

    if sample_rate <= 0:
        raise ValueError(f"invalid WAV sample_rate: {sample_rate}")

    if allowed_sample_rates and sample_rate not in allowed_sample_rates:
        raise ValueError(
            f"sample_rate {sample_rate} not in AUDIO_ALLOWED_SAMPLE_RATES "
            f"{allowed_sample_rates}"
        )
    if allowed_channels and channels not in allowed_channels:
        raise ValueError(
            f"channels {channels} not in AUDIO_ALLOWED_CHANNELS {allowed_channels}"
        )

    duration_seconds = float(n_frames) / float(sample_rate)
    checksum = _compute_sha256(p)

    return AudioMetadata(
        path=p,
        size_bytes=size,
        sample_rate=sample_rate,
        channels=channels,
        sample_width_bytes=sample_width,
        n_frames=n_frames,
        duration_seconds=duration_seconds,
        checksum_sha256=checksum,
        mime_type=mime_type,
    )
