"""Editor — Phase 3H edit_plan + Phase 9D real / metadata-only reel_draft.

Reads the structured script artifact produced by the scriptwriter stage
and emits a deterministic ``EditPlan`` artifact (Phase 3H semantics):

- Splits the target duration across ``hook`` (20%), ``body`` (65%),
  ``cta`` (15%) of ``target_duration_seconds``.
- Computes durations in **milliseconds** internally so segments tile
  exactly from 0 to the target without float drift.
- Carries the script text per segment and a reference to the source
  script (uri + checksum) so downstream stages can audit provenance.

Phase 9D — real reel_draft when upstream video is real:

- If the lipsync stage produced a real ``talking_head`` ArtifactRef
  (``local_path`` set, ``checksum_sha256`` set, ``mime_type=video/mp4``,
  file on disk, size > 0), the editor runs a single ``ffmpeg`` subprocess
  to remux the source into a controlled output path. The output is
  validated (file exists, size > 0, sha256 computed) and returned as a
  real ``ArtifactRef`` with ``extra.real_editor_output=True``,
  ``extra.editor_mode="ffmpeg_remux"``.
- If ffmpeg is not on PATH and a real upstream exists, the stage raises
  ``StageRejection("editor_ffmpeg_missing")`` — no phantom MP4 is
  registered. Cleanup of any partial output happens before we raise.
- If the upstream is metadata-only (the Phase 9B placeholder face stub
  or a Phase 7B no-op lipsync), the editor emits a clearly-labelled
  *metadata-only* reel_draft placeholder: ``placeholder://`` URI, no
  ``.mp4``, no ``local_path``, no ``checksum``,
  ``extra.real_editor_output=False``,
  ``extra.editor_mode="metadata_only"``,
  ``extra.reason="no_real_video_artifact"``.

No moviepy / OpenCV / numpy. ffmpeg is invoked via ``subprocess`` with
an arg list (no ``shell=True``), a timeout, and partial-output cleanup.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from common.enums import ArtifactType, StageName
from common.exceptions import StageRejection
from common.schemas import ArtifactRef, DagState, EditPlan, EditSegment, StageOutput


_FFMPEG_TIMEOUT_SECONDS = 60
_REEL_DRAFT_SIZE_LIMIT_BYTES = 5 * 1024 * 1024 * 1024  # 5 GB belt-and-braces


def _stub_uri(job_id: str, filename: str) -> str:
    return f"s3://aivideo-jobs/{job_id}/{filename}"


def _placeholder_reel_draft_uri(job_id: str) -> str:
    return f"placeholder://editor/{job_id}/no-real-video-artifact"


def _artifacts_video_dir(job_id: str) -> Path:
    base_root = os.environ.get("ARTIFACTS_LOCAL_ROOT") or tempfile.gettempdir()
    out_dir = Path(base_root) / "video" / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _has_real_upstream_video(talking_head: ArtifactRef | None) -> bool:
    if talking_head is None:
        return False
    if not talking_head.local_path or not talking_head.checksum_sha256:
        return False
    if talking_head.mime_type and talking_head.mime_type != "video/mp4":
        return False
    p = Path(talking_head.local_path)
    if not p.is_file():
        return False
    try:
        return 0 < p.stat().st_size <= _REEL_DRAFT_SIZE_LIMIT_BYTES
    except OSError:
        return False


def _safe_cleanup(p: Path) -> None:
    try:
        if p.is_file():
            p.unlink()
    except Exception:  # noqa: BLE001
        pass


# Phase 22 — orientation → (width, height) for talking_head output.
_ORIENTATION_DIMS: dict[str, tuple[int, int]] = {
    "landscape": (1280, 720),
    "portrait": (720, 1280),
    "square": (1024, 1024),
}


def _ffmpeg_remux(
    src: Path,
    dst: Path,
    burn_in_subtitle: Path | None = None,
    orientation: str = "landscape",
) -> None:
    """Remux ``src`` to ``dst``.

    Default path: stream-copy (no re-encode, fast).

    Phase 21 — ``burn_in_subtitle`` re-encodes with a ``subtitles=``
    filter so captions bake into pixels.
    Phase 22 — non-square ``orientation`` adds a scale-fit + black-pad
    filter so the (square) SadTalker output becomes a 9:16 portrait /
    1:1 square reel. When both apply, the filters chain
    (scale-pad → subtitles).
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise StageRejection(
            StageName.editor.value,
            (
                "editor_ffmpeg_missing: real reel_draft composition requires "
                "ffmpeg on PATH; install ffmpeg or fall back to the "
                "metadata-only editor mode by clearing the upstream "
                "talking_head local_path."
            ),
        )
    orient = (orientation or "landscape").lower()
    # talking_head SadTalker output is square; only re-encode-pad when
    # the operator picked portrait or square (square still benefits from
    # a clean canonical size). Landscape keeps the fast stream-copy path
    # unless subtitles force a re-encode.
    needs_orient_pad = orient in ("portrait", "square")

    cmd: list[str]
    vf_parts: list[str] = []

    if needs_orient_pad:
        w, h = _ORIENTATION_DIMS.get(orient, _ORIENTATION_DIMS["landscape"])
        vf_parts.append(
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
        )

    if burn_in_subtitle is not None and burn_in_subtitle.is_file():
        safe_name = f"_subs_{dst.stem}.{burn_in_subtitle.suffix.lstrip('.') or 'srt'}"
        safe_path = dst.parent / safe_name
        try:
            safe_path.write_bytes(burn_in_subtitle.read_bytes())
        except OSError as exc:
            raise StageRejection(
                StageName.editor.value,
                f"editor_subtitle_copy_failed: {exc}",
            ) from exc
        escaped_path = str(safe_path).replace("\\", "\\\\").replace(":", r"\:")
        vf_parts.append(
            f"subtitles={escaped_path}"
            ":force_style='FontName=DejaVu Sans,Fontsize=22,"
            "PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,"
            "BorderStyle=3,Outline=1,Shadow=0,Alignment=2,MarginV=30'"
        )

    if vf_parts:
        cmd = [
            ffmpeg, "-y", "-i", str(src),
            "-vf", ",".join(vf_parts),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "copy",
            str(dst),
        ]
    else:
        cmd = [ffmpeg, "-y", "-i", str(src), "-c", "copy", str(dst)]
    try:
        proc = subprocess.run(  # noqa: S603 — arg list, no shell
            cmd,
            capture_output=True,
            timeout=_FFMPEG_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        _safe_cleanup(dst)
        raise StageRejection(
            StageName.editor.value,
            f"editor_ffmpeg_timeout: ffmpeg exceeded {_FFMPEG_TIMEOUT_SECONDS}s",
        ) from exc
    if proc.returncode != 0:
        _safe_cleanup(dst)
        tail = proc.stderr.decode("utf-8", errors="replace")[-500:]
        raise StageRejection(
            StageName.editor.value,
            f"editor_ffmpeg_failed: returncode={proc.returncode}; stderr_tail={tail!r}",
        )
    if not dst.is_file() or dst.stat().st_size == 0:
        _safe_cleanup(dst)
        raise StageRejection(
            StageName.editor.value,
            "editor_ffmpeg_failed: ffmpeg returned 0 but output is missing/empty",
        )


def _build_real_reel_draft(
    *,
    job_id: str,
    talking_head: ArtifactRef,
    edit_plan_uri: str,
    edit_plan_checksum: str,
    subtitle_burn_in_path: Path | None = None,
    orientation: str = "landscape",
) -> ArtifactRef:
    src = Path(talking_head.local_path or "")
    out_dir = _artifacts_video_dir(job_id)
    out_path = out_dir / f"reel_draft_{uuid.uuid4().hex}.mp4"
    _ffmpeg_remux(
        src, out_path,
        burn_in_subtitle=subtitle_burn_in_path,
        orientation=orientation,
    )
    size_bytes = out_path.stat().st_size
    checksum = _sha256_of_file(out_path)
    burned_in = subtitle_burn_in_path is not None and subtitle_burn_in_path.is_file()
    return ArtifactRef(
        artifact_type=ArtifactType.video.value,
        uri=out_path.as_uri(),
        local_path=str(out_path),
        mime_type="video/mp4",
        checksum_sha256=checksum,
        size_bytes=size_bytes,
        duration_seconds=talking_head.duration_seconds,
        width=talking_head.width,
        height=talking_head.height,
        extra={
            "phase": "phase21_editor_remux_with_subtitle_burnin",
            "real_editor_output": True,
            "editor_mode": "ffmpeg_burnin" if burned_in else "ffmpeg_remux",
            "input_video_uri": talking_head.uri,
            "input_video_checksum": talking_head.checksum_sha256,
            "input_video_local_path": talking_head.local_path,
            "edit_plan_uri": edit_plan_uri,
            "edit_plan_checksum": edit_plan_checksum,
            "watermark_burned_in": False,
            "subtitles_burned_in": burned_in,
            "subtitle_source_path": (
                str(subtitle_burn_in_path) if subtitle_burn_in_path else None
            ),
        },
    )


def _build_metadata_only_reel_draft(
    *,
    job_id: str,
    edit_plan_uri: str,
    edit_plan_checksum: str,
    reason: str,
    upstream_uri: str | None,
) -> ArtifactRef:
    return ArtifactRef(
        artifact_type=ArtifactType.video.value,
        uri=_placeholder_reel_draft_uri(job_id),
        extra={
            "phase": "phase9d_metadata_only",
            "real_editor_output": False,
            "editor_mode": "metadata_only",
            "reason": reason,
            "is_placeholder": True,
            "edit_plan_uri": edit_plan_uri,
            "edit_plan_checksum": edit_plan_checksum,
            "upstream_talking_head_uri": upstream_uri,
            "watermark_burned_in": False,
        },
    )


def _allocate_timings_ms(target_seconds: float) -> tuple[int, int, int]:
    """Return (hook_ms, body_ms, cta_ms) summing exactly to round(target*1000)."""
    target_ms = round(target_seconds * 1000)
    hook_ms = round(target_ms * 0.20)
    cta_ms = round(target_ms * 0.15)
    body_ms = target_ms - hook_ms - cta_ms
    return hook_ms, body_ms, cta_ms


# Phase 5C fit-classification windows. Kept in sync with
# ``backend/app/api/audio_fit.py`` so the operator sees the same
# verdict whether they hit the live fit-check endpoint or read the
# embedded fit metadata on the edit_plan artifact.
_FIT_OK_WINDOW_SECONDS = 1.0
_FIT_SOFT_WINDOW_SECONDS = 3.0


def _classify_fit(
    target_seconds: float, audio_duration_seconds: float | None
) -> tuple[str, str, float | None]:
    if audio_duration_seconds is None:
        return "missing_audio", "upload_better_audio", None
    delta = round(audio_duration_seconds - target_seconds, 3)
    abs_delta = abs(delta)
    if abs_delta <= _FIT_OK_WINDOW_SECONDS:
        return "ok", "accept", delta
    if delta < 0:
        if abs_delta <= _FIT_SOFT_WINDOW_SECONDS:
            return "too_short", "regenerate_script_longer", delta
        return "too_short", "adjust_target_duration", delta
    if abs_delta <= _FIT_SOFT_WINDOW_SECONDS:
        return "too_long", "regenerate_script_shorter", delta
    return "too_long", "adjust_target_duration", delta


def _build_edit_plan(
    *,
    target_seconds: float,
    hook_text: str,
    body_text: str,
    cta_text: str,
    source_uri: str,
    source_checksum: str | None,
    audio_duration_seconds: float | None = None,
) -> EditPlan:
    h_ms, b_ms, c_ms = _allocate_timings_ms(target_seconds)
    # Convert ms → seconds for the schema fields. Division by 1000 keeps
    # arithmetic predictable; the validator compares in ms so float
    # representations like 28.049999... still pass.
    segments = [
        EditSegment(
            segment_type="hook",
            start_seconds=0.0,
            end_seconds=h_ms / 1000.0,
            duration_seconds=h_ms / 1000.0,
            text=hook_text,
        ),
        EditSegment(
            segment_type="body",
            start_seconds=h_ms / 1000.0,
            end_seconds=(h_ms + b_ms) / 1000.0,
            duration_seconds=b_ms / 1000.0,
            text=body_text,
        ),
        EditSegment(
            segment_type="cta",
            start_seconds=(h_ms + b_ms) / 1000.0,
            end_seconds=(h_ms + b_ms + c_ms) / 1000.0,
            duration_seconds=c_ms / 1000.0,
            text=cta_text,
        ),
    ]
    fit_status, recommendation, delta_seconds = _classify_fit(
        target_seconds, audio_duration_seconds
    )
    metadata: dict = {
        "allocation": {"hook_pct": 0.20, "body_pct": 0.65, "cta_pct": 0.15},
        "phase": "phase3h",
        # Phase 5C: embed the audio-fit verdict so downstream stages
        # (qc, publisher) and the UI can read it without hitting the
        # live /api/v1/audio/fit-check endpoint.
        "audio_duration_seconds": audio_duration_seconds,
        "duration_delta_seconds": delta_seconds,
        "fit_status": fit_status,
        "recommendation": recommendation,
    }
    return EditPlan(
        target_duration_seconds=float(round(target_seconds, 3)),
        source_script_uri=source_uri,
        source_script_checksum=source_checksum,
        segments=segments,
        metadata=metadata,
    )


async def run(state: DagState) -> StageOutput:
    if not state.watermark_required:
        raise StageRejection(StageName.editor.value, "watermark_required must be true")

    # Existing: lipsync output must be present for the downstream qc stage.
    talking_head_output = state.stage_outputs.get(StageName.lipsync.value)
    if talking_head_output is None or "talking_head" not in talking_head_output.artifacts:
        raise StageRejection(StageName.editor.value, "upstream lipsync missing talking_head")

    # Phase 3H: scriptwriter output must be present so we can derive timings.
    script_output = state.stage_outputs.get(StageName.scriptwriter.value)
    if script_output is None or "script" not in script_output.artifacts:
        raise StageRejection(
            StageName.editor.value,
            "upstream scriptwriter missing 'script' artifact — cannot build edit_plan",
        )
    script_ref = script_output.artifacts["script"]
    structured = script_ref.extra.get("structured_script") if isinstance(script_ref.extra, dict) else None
    if not isinstance(structured, dict):
        raise StageRejection(
            StageName.editor.value,
            "script artifact is missing extra.structured_script metadata",
        )

    target = float(state.target_duration_seconds)
    if target <= 0:
        raise StageRejection(
            StageName.editor.value,
            f"invalid target_duration_seconds: {target}",
        )

    # Phase 5C: pull audio duration from the voice stage if present so the
    # edit_plan records a fit verdict. Voice handler populates
    # ``ArtifactRef.duration_seconds`` from the WAV inspector (real path)
    # or from the operator-supplied AudioRef (provided_audio).
    audio_duration_seconds: float | None = None
    voice_output = state.stage_outputs.get(StageName.voice.value)
    if voice_output is not None:
        for ref in voice_output.artifacts.values():
            if ref.artifact_type == ArtifactType.audio.value and ref.duration_seconds:
                audio_duration_seconds = float(ref.duration_seconds)
                break

    try:
        plan = _build_edit_plan(
            target_seconds=target,
            hook_text=str(structured.get("hook", "")),
            body_text=str(structured.get("body", "")),
            cta_text=str(structured.get("cta", "")),
            source_uri=script_ref.uri,
            source_checksum=script_ref.checksum_sha256,
            audio_duration_seconds=audio_duration_seconds,
        )
    except ValueError as exc:
        raise StageRejection(StageName.editor.value, f"failed to build edit_plan: {exc}") from exc

    plan_json = plan.model_dump_json()
    plan_bytes = plan_json.encode("utf-8")
    plan_sha = hashlib.sha256(plan_bytes).hexdigest()

    edit_plan_ref = ArtifactRef(
        artifact_type=ArtifactType.edit_plan.value,
        uri=_stub_uri(str(state.job_id), "edit_plan.json"),
        mime_type="application/json",
        checksum_sha256=plan_sha,
        size_bytes=len(plan_bytes),
        duration_seconds=plan.target_duration_seconds,
        extra={
            "phase": "phase3h",
            "edit_plan": json.loads(plan_json),
            "source_script_uri": script_ref.uri,
            "source_script_checksum": script_ref.checksum_sha256,
            "segment_count": len(plan.segments),
            "no_video_generated": True,
        },
    )

    # Phase 9D: branch on whether the upstream lipsync stage handed us a
    # real ``talking_head`` MP4 (local_path + checksum + on-disk file).
    # Yes → ffmpeg remux to a controlled output and emit a real
    # reel_draft. No → emit a clearly-labelled metadata-only placeholder
    # so the downstream QC stage still has the ``reel_draft`` key it
    # needs but cannot mistake it for a real video.
    talking_head_ref = talking_head_output.artifacts["talking_head"]
    real_video_upstream = _has_real_upstream_video(talking_head_ref)
    if real_video_upstream:
        # Phase 21 — burn in subtitles when the operator opted in AND
        # the orchestrator was able to locate the sidecar SRT/VTT file.
        burn_in_path: Path | None = None
        if state.subtitle_burn_in and state.subtitle_artifact_local_path:
            candidate = Path(state.subtitle_artifact_local_path)
            if candidate.is_file():
                burn_in_path = candidate
        reel_draft_ref = _build_real_reel_draft(
            job_id=str(state.job_id),
            talking_head=talking_head_ref,
            edit_plan_uri=edit_plan_ref.uri,
            edit_plan_checksum=plan_sha,
            subtitle_burn_in_path=burn_in_path,
            orientation=getattr(state, "orientation", "landscape"),
        )
        notes = (
            "editor produced deterministic edit_plan and ffmpeg-"
            + ("burned subtitles into" if burn_in_path else "remuxed")
            + " a real reel_draft from the upstream lipsync MP4"
        )
    else:
        reel_draft_ref = _build_metadata_only_reel_draft(
            job_id=str(state.job_id),
            edit_plan_uri=edit_plan_ref.uri,
            edit_plan_checksum=plan_sha,
            reason="no_real_video_artifact",
            upstream_uri=talking_head_ref.uri if talking_head_ref else None,
        )
        notes = (
            "editor produced deterministic edit_plan; upstream lipsync is "
            "metadata-only so reel_draft is a metadata-only placeholder "
            "(no real video file emitted)"
        )

    return StageOutput(
        noop=False,
        notes=notes,
        artifacts={"edit_plan": edit_plan_ref, "reel_draft": reel_draft_ref},
    )
