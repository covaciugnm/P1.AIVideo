"""Phase 8C — real media QC.

Inspects an on-disk media artifact (video / final_export MP4) using
ffprobe + deterministic file checks. Produces a structured report
the API + frontend pattern-match. **No ML metrics** (sync confidence,
identity match, OCR) — those land in a future phase. Everything here
is deterministic, bounded, and runs without GPU.

Design:

- ``inspect_media_artifact(...)`` takes either a DB ``Artifact`` row
  or a raw path + optional expected fields, runs every check it can,
  and returns a ``MediaQcReport`` dataclass. **Never raises**.
- ``MediaQcReport.passed`` is true only when zero ``fail`` decisions
  fired and at least the file-exists / file-non-empty / video-stream
  checks ran successfully.
- Warnings (``warn`` decisions) do not flip ``passed=false`` — they're
  informative (e.g. missing audio stream, duration delta > tolerance).
- The report's ``checks`` list carries the same ``QCCheck`` shape the
  Phase 3I DAG QC handler uses so a future merged report renders the
  same way.

Reuses Phase 8A's bounded ``video_inspection.inspect_video()`` for
ffprobe — single source of truth for ffprobe argv + timeout.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.services.video_inspection import VideoMetadata, has_ffprobe, inspect_video


_DURATION_WARN_DELTA_SECONDS = 1.0  # ≥1 s drift from expected → warn
_DURATION_FAIL_DELTA_SECONDS = 5.0  # ≥5 s drift → fail


CheckDecision = Literal["pass", "fail", "warn", "skip"]


@dataclass(frozen=True)
class MediaCheck:
    """One check from a media-QC run. Mirrors common.schemas.QCCheck so
    a future merged JSON serialization is identical."""

    name: str
    decision: CheckDecision
    detail: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "decision": self.decision,
            "detail": self.detail,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class MediaQcReport:
    """Result of ``inspect_media_artifact()``.

    ``passed`` is true only when zero ``fail`` decisions fired. Warnings
    (``warn``) are informative; ``skip`` decisions reflect checks the
    inspector couldn't reach (e.g. ffprobe missing).
    """

    passed: bool
    file_size_bytes: int | None
    duration_seconds: float | None
    width: int | None
    height: int | None
    container_format: str | None
    video_codec: str | None
    audio_codec: str | None
    video_stream_present: bool
    audio_stream_present: bool
    duration_delta_seconds: float | None
    expected_duration_seconds: float | None
    checksum_sha256: str | None
    mime_type: str | None
    checks: list[MediaCheck]
    warnings: list[str]
    failures: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "file_size_bytes": self.file_size_bytes,
            "duration_seconds": self.duration_seconds,
            "width": self.width,
            "height": self.height,
            "container_format": self.container_format,
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
            "video_stream_present": self.video_stream_present,
            "audio_stream_present": self.audio_stream_present,
            "duration_delta_seconds": self.duration_delta_seconds,
            "expected_duration_seconds": self.expected_duration_seconds,
            "checksum_sha256": self.checksum_sha256,
            "mime_type": self.mime_type,
            "checks": [c.to_dict() for c in self.checks],
            "warnings": list(self.warnings),
            "failures": list(self.failures),
        }


def _compute_sha256(path: Path, *, max_bytes: int) -> str | None:
    """Hash up to ``max_bytes`` of the file. Returns None if the file
    is gone mid-read."""
    h = hashlib.sha256()
    read = 0
    try:
        with path.open("rb") as f:
            while read < max_bytes:
                chunk = f.read(min(64 * 1024, max_bytes - read))
                if not chunk:
                    break
                h.update(chunk)
                read += len(chunk)
    except OSError:
        return None
    return h.hexdigest()


def inspect_media_artifact(
    *,
    path: Path | str,
    mime_type: str | None = None,
    expected_duration_seconds: float | None = None,
    expected_checksum_sha256: str | None = None,
    require_audio: bool = False,
    max_hash_bytes: int = 100 * 1024 * 1024,  # 100 MB cap for hashing
) -> MediaQcReport:
    """Inspect a media file and produce a structured QC report.

    Parameters (all optional except ``path``):

    - ``mime_type``                 — caller's recorded mime; included
                                       in the report but **not** trusted.
    - ``expected_duration_seconds`` — if provided, drives the
                                       duration-delta warn/fail.
    - ``expected_checksum_sha256``  — if provided, the inspector
                                       recomputes and compares.
    - ``require_audio``             — when True, a missing audio stream
                                       fails (default: warn).
    - ``max_hash_bytes``            — soft cap on bytes we hash so a
                                       huge file doesn't hang the
                                       request. Hashing 100 MB takes
                                       well under a second.
    """
    checks: list[MediaCheck] = []
    warnings: list[str] = []
    failures: list[str] = []
    p = Path(path)

    # 1. Path safety: must be absolute. Caller is responsible for the
    # allowed-roots check; we just bounce relative paths.
    if not p.is_absolute():
        checks.append(
            MediaCheck(
                name="path_absolute",
                decision="fail",
                detail=f"path is not absolute: {p}",
            )
        )
        failures.append("path_absolute")
        return _build_failed_report(
            checks=checks,
            warnings=warnings,
            failures=failures,
            mime_type=mime_type,
            expected_duration_seconds=expected_duration_seconds,
        )
    checks.append(MediaCheck(name="path_absolute", decision="pass"))

    # 2. File exists.
    if not p.exists() or not p.is_file():
        checks.append(
            MediaCheck(
                name="file_exists",
                decision="fail",
                detail=f"file not on disk: {p}",
            )
        )
        failures.append("file_exists")
        return _build_failed_report(
            checks=checks,
            warnings=warnings,
            failures=failures,
            mime_type=mime_type,
            expected_duration_seconds=expected_duration_seconds,
        )
    checks.append(MediaCheck(name="file_exists", decision="pass"))

    # 3. Size > 0.
    size_bytes = p.stat().st_size
    if size_bytes == 0:
        checks.append(
            MediaCheck(
                name="file_size_positive",
                decision="fail",
                detail="file is zero bytes",
                metadata={"size_bytes": 0},
            )
        )
        failures.append("file_size_positive")
        return _build_failed_report(
            file_size_bytes=0,
            checks=checks,
            warnings=warnings,
            failures=failures,
            mime_type=mime_type,
            expected_duration_seconds=expected_duration_seconds,
        )
    checks.append(
        MediaCheck(
            name="file_size_positive",
            decision="pass",
            detail=f"{size_bytes} bytes",
            metadata={"size_bytes": size_bytes},
        )
    )

    # 4. Optional checksum match.
    actual_checksum: str | None = None
    if expected_checksum_sha256:
        if size_bytes > max_hash_bytes:
            checks.append(
                MediaCheck(
                    name="checksum_match",
                    decision="skip",
                    detail=(
                        f"file ({size_bytes} bytes) exceeds hash cap "
                        f"({max_hash_bytes}); skipping recompute"
                    ),
                )
            )
        else:
            actual_checksum = _compute_sha256(p, max_bytes=max_hash_bytes)
            if actual_checksum is None:
                checks.append(
                    MediaCheck(
                        name="checksum_match",
                        decision="fail",
                        detail="could not read file for checksum",
                    )
                )
                failures.append("checksum_match")
            elif actual_checksum != expected_checksum_sha256:
                checks.append(
                    MediaCheck(
                        name="checksum_match",
                        decision="fail",
                        detail="recomputed checksum does not match expected",
                        metadata={
                            "expected": expected_checksum_sha256,
                            "actual": actual_checksum,
                        },
                    )
                )
                failures.append("checksum_match")
            else:
                checks.append(
                    MediaCheck(
                        name="checksum_match",
                        decision="pass",
                        detail=f"matches {actual_checksum[:12]}…",
                    )
                )

    # 5. ffprobe-driven stream checks.
    if not has_ffprobe():
        checks.append(
            MediaCheck(
                name="ffprobe_inspection",
                decision="skip",
                detail="ffprobe not on PATH; container/stream checks skipped",
            )
        )
        warnings.append("ffprobe_inspection_skipped")
        # We still produced size + file-exists checks; passed depends
        # on whether anything else failed.
        return _finalize_report(
            file_size_bytes=size_bytes,
            checksum_sha256=actual_checksum,
            mime_type=mime_type,
            expected_duration_seconds=expected_duration_seconds,
            metadata=VideoMetadata(available=False, reason="ffprobe_missing"),
            checks=checks,
            warnings=warnings,
            failures=failures,
        )

    info = inspect_video(p)
    if not info.available:
        checks.append(
            MediaCheck(
                name="ffprobe_inspection",
                decision="fail",
                detail=f"ffprobe could not parse the file: {info.reason}",
                metadata={"reason": info.reason},
            )
        )
        failures.append("ffprobe_inspection")
        return _finalize_report(
            file_size_bytes=size_bytes,
            checksum_sha256=actual_checksum,
            mime_type=mime_type,
            expected_duration_seconds=expected_duration_seconds,
            metadata=info,
            checks=checks,
            warnings=warnings,
            failures=failures,
        )

    checks.append(
        MediaCheck(
            name="ffprobe_inspection",
            decision="pass",
            detail=f"container={info.container_format}, codec={info.video_codec}",
        )
    )

    # 6. Video stream present.
    if not info.video_stream_present:
        checks.append(
            MediaCheck(
                name="video_stream_present",
                decision="fail",
                detail="ffprobe found no video stream",
            )
        )
        failures.append("video_stream_present")
    else:
        checks.append(
            MediaCheck(
                name="video_stream_present",
                decision="pass",
                detail=f"{info.width}×{info.height} {info.video_codec}",
            )
        )

    # 7. Audio stream — fail-or-warn depending on require_audio.
    if not info.audio_stream_present:
        if require_audio:
            checks.append(
                MediaCheck(
                    name="audio_stream_present",
                    decision="fail",
                    detail="audio stream required but absent",
                )
            )
            failures.append("audio_stream_present")
        else:
            checks.append(
                MediaCheck(
                    name="audio_stream_present",
                    decision="warn",
                    detail="no audio stream (caller did not require one)",
                )
            )
            warnings.append("audio_stream_absent")
    else:
        checks.append(
            MediaCheck(
                name="audio_stream_present",
                decision="pass",
                detail=f"audio codec={info.audio_codec}",
            )
        )

    # 8. Duration delta.
    duration_delta: float | None = None
    if expected_duration_seconds is not None and info.duration_seconds is not None:
        duration_delta = abs(info.duration_seconds - expected_duration_seconds)
        if duration_delta >= _DURATION_FAIL_DELTA_SECONDS:
            checks.append(
                MediaCheck(
                    name="duration_within_tolerance",
                    decision="fail",
                    detail=(
                        f"duration {info.duration_seconds:.2f}s drifts "
                        f"{duration_delta:.2f}s from target "
                        f"{expected_duration_seconds:.2f}s (>= "
                        f"{_DURATION_FAIL_DELTA_SECONDS}s fail threshold)"
                    ),
                    metadata={"delta": duration_delta},
                )
            )
            failures.append("duration_within_tolerance")
        elif duration_delta >= _DURATION_WARN_DELTA_SECONDS:
            checks.append(
                MediaCheck(
                    name="duration_within_tolerance",
                    decision="warn",
                    detail=(
                        f"duration {info.duration_seconds:.2f}s drifts "
                        f"{duration_delta:.2f}s from target "
                        f"{expected_duration_seconds:.2f}s"
                    ),
                    metadata={"delta": duration_delta},
                )
            )
            warnings.append("duration_drift")
        else:
            checks.append(
                MediaCheck(
                    name="duration_within_tolerance",
                    decision="pass",
                    detail=f"Δ={duration_delta:.3f}s",
                )
            )
    elif expected_duration_seconds is not None:
        checks.append(
            MediaCheck(
                name="duration_within_tolerance",
                decision="skip",
                detail="ffprobe did not report a duration",
            )
        )

    return _finalize_report(
        file_size_bytes=size_bytes,
        checksum_sha256=actual_checksum,
        mime_type=mime_type,
        expected_duration_seconds=expected_duration_seconds,
        metadata=info,
        checks=checks,
        warnings=warnings,
        failures=failures,
        duration_delta=duration_delta,
    )


def _build_failed_report(
    *,
    file_size_bytes: int | None = None,
    checks: list[MediaCheck],
    warnings: list[str],
    failures: list[str],
    mime_type: str | None,
    expected_duration_seconds: float | None,
) -> MediaQcReport:
    return MediaQcReport(
        passed=False,
        file_size_bytes=file_size_bytes,
        duration_seconds=None,
        width=None,
        height=None,
        container_format=None,
        video_codec=None,
        audio_codec=None,
        video_stream_present=False,
        audio_stream_present=False,
        duration_delta_seconds=None,
        expected_duration_seconds=expected_duration_seconds,
        checksum_sha256=None,
        mime_type=mime_type,
        checks=checks,
        warnings=warnings,
        failures=failures,
    )


def _finalize_report(
    *,
    file_size_bytes: int,
    checksum_sha256: str | None,
    mime_type: str | None,
    expected_duration_seconds: float | None,
    metadata: VideoMetadata,
    checks: list[MediaCheck],
    warnings: list[str],
    failures: list[str],
    duration_delta: float | None = None,
) -> MediaQcReport:
    return MediaQcReport(
        passed=len(failures) == 0,
        file_size_bytes=file_size_bytes,
        duration_seconds=metadata.duration_seconds,
        width=metadata.width,
        height=metadata.height,
        container_format=metadata.container_format,
        video_codec=metadata.video_codec,
        audio_codec=metadata.audio_codec,
        video_stream_present=metadata.video_stream_present,
        audio_stream_present=metadata.audio_stream_present,
        duration_delta_seconds=duration_delta,
        expected_duration_seconds=expected_duration_seconds,
        checksum_sha256=checksum_sha256,
        mime_type=mime_type,
        checks=checks,
        warnings=warnings,
        failures=failures,
    )
