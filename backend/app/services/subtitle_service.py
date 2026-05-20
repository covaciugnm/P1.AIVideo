"""Phase 11A — basic SRT / VTT subtitle generator.

Produces a sidecar subtitle artifact per requested language. The timing
is **approximate** — we evenly distribute the script across the
``target_duration_seconds`` window. Real forced alignment lives in a
future phase; the metadata records ``alignment="approximate"`` so the
operator + downstream consumers never confuse this with phoneme-level
captions.

No external dependencies; stdlib only.
"""
from __future__ import annotations

import hashlib
import os
import re
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from common.enums import ArtifactType

from app.core.config import settings
from app.services import artifact_service


# ---------------------------------------------------------------------------
# Tiny text segmentation — no NLP, just sentence/punctuation heuristics.
# ---------------------------------------------------------------------------

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _split_into_cues(text: str, *, max_cues: int = 12) -> list[str]:
    """Break text into 2–``max_cues`` cue strings.

    1. Split on sentence punctuation. Romanian + English share `.!?`.
    2. If we still have a single very long sentence, split on commas.
    3. Cap at ``max_cues`` — additional sentences are merged into the
       last cue.
    """
    chunks = [c.strip() for c in _SENTENCE_SPLIT.split(text) if c.strip()]
    if len(chunks) < 2:
        # Fall back to comma-split for monolithic inputs.
        chunks = [c.strip() for c in re.split(r"(?<=,)\s+", text) if c.strip()]
    if not chunks:
        chunks = [text.strip() or "(empty script)"]
    if len(chunks) > max_cues:
        head = chunks[: max_cues - 1]
        tail = " ".join(chunks[max_cues - 1 :])
        chunks = head + [tail]
    return chunks


def _format_timecode_srt(seconds: float) -> str:
    """``HH:MM:SS,mmm`` — SRT spec uses a comma decimal separator."""
    ms = int(round(seconds * 1000))
    hh, rem = divmod(ms, 3_600_000)
    mm, rem = divmod(rem, 60_000)
    ss, ms = divmod(rem, 1000)
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"


def _format_timecode_vtt(seconds: float) -> str:
    """``HH:MM:SS.mmm`` — WebVTT uses a period decimal separator."""
    return _format_timecode_srt(seconds).replace(",", ".")


def render_srt(cues: list[str], total_seconds: float) -> str:
    if not cues:
        return ""
    span = max(total_seconds / len(cues), 0.5)
    lines: list[str] = []
    for i, text in enumerate(cues, start=1):
        start = (i - 1) * span
        end = i * span
        lines.append(str(i))
        lines.append(f"{_format_timecode_srt(start)} --> {_format_timecode_srt(end)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def render_vtt(cues: list[str], total_seconds: float) -> str:
    if not cues:
        return "WEBVTT\n"
    span = max(total_seconds / len(cues), 0.5)
    lines = ["WEBVTT", ""]
    for i, text in enumerate(cues, start=1):
        start = (i - 1) * span
        end = i * span
        lines.append(f"{_format_timecode_vtt(start)} --> {_format_timecode_vtt(end)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


# ---------------------------------------------------------------------------
# File + artifact registration
# ---------------------------------------------------------------------------


_MIME_BY_FORMAT: dict[str, str] = {
    "srt": "application/x-subrip",
    "vtt": "text/vtt",
}


def _subtitle_root() -> Path:
    """Default to ``$ARTIFACTS_LOCAL_ROOT/subtitles`` so the content
    endpoint can serve the bytes from the same volume as everything else.
    """
    return Path(
        os.environ.get("ARTIFACTS_LOCAL_ROOT") or settings.artifacts_local_root
    ) / "subtitles"


def _write_subtitle_file(
    *,
    job_id: uuid.UUID,
    language_code: str,
    fmt: str,
    body: str,
) -> Path:
    base = _subtitle_root() / str(job_id)
    base.mkdir(parents=True, exist_ok=True)
    try:
        base.chmod(0o777)
    except OSError:
        pass
    out = base / f"{language_code}.{fmt}"
    out.write_text(body, encoding="utf-8")
    try:
        out.chmod(0o666)
    except OSError:
        pass
    return out


async def generate_subtitle_artifacts(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    script_text: str,
    languages: list[str],
    fmt: str = "srt",
    target_duration_seconds: float | None = None,
    burn_in_requested: bool = False,
) -> list[uuid.UUID]:
    """Write one subtitle file per language; register each as an
    ``ArtifactType.subtitle`` row. Returns the new artifact ids.

    Timing is approximate (evenly-spaced cues). Real alignment requires
    forced-alignment infra not present in Phase 11A; the metadata
    records this so consumers don't claim phoneme-level captions.
    """
    if not script_text.strip() or not languages:
        return []
    cues = _split_into_cues(script_text.strip())
    total = float(target_duration_seconds or max(len(cues) * 2.5, 2.0))

    mime = _MIME_BY_FORMAT.get(fmt, "text/plain")
    render = render_vtt if fmt == "vtt" else render_srt

    new_ids: list[uuid.UUID] = []
    for lang in languages:
        body = render(cues, total)
        path = _write_subtitle_file(
            job_id=job_id, language_code=lang, fmt=fmt, body=body
        )
        size_bytes = path.stat().st_size
        checksum = hashlib.sha256(body.encode("utf-8")).hexdigest()
        art = await artifact_service.register_artifact(
            session,
            job_id=job_id,
            artifact_type=ArtifactType.subtitle.value,
            uri=path.as_uri(),
            local_path=str(path),
            mime_type=mime,
            checksum_sha256=checksum,
            size_bytes=size_bytes,
            metadata_json={
                "phase": "phase11a_subtitle_sidecar",
                "language_code": lang,
                "format": fmt,
                "cue_count": len(cues),
                "approximate_total_seconds": total,
                "source": "generated_from_script",
                "alignment": "approximate",
                "real_timing": False,
                "burn_in_requested": burn_in_requested,
                # Phase 21 — burn-in is now wired through the orchestrator
                # → editor stage (ffmpeg subtitles= filter). The actual
                # bake happens when the DAG runs; this row only records
                # the operator's INTENT.
                "burn_in_status": (
                    "queued_for_editor" if burn_in_requested else "sidecar_only"
                ),
            },
        )
        new_ids.append(art.id)
    return new_ids
