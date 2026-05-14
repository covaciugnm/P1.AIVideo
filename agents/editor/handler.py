"""Editor — Phase 3H: deterministic edit plan from the structured script.

Reads the structured script artifact produced by the scriptwriter stage
(Phase 3G) and emits a deterministic ``EditPlan`` artifact:

- Splits the target duration across ``hook`` (20%), ``body`` (65%),
  ``cta`` (15%) of ``target_duration_seconds``.
- Computes durations in **milliseconds** internally so segments tile
  exactly from 0 to the target without float drift.
- Carries the script text per segment and a reference to the source
  script (uri + checksum) so downstream stages can audit provenance.

Phase 3H stays metadata-only. The existing ``reel_draft.mp4`` stub stays
in the editor's output so the downstream QC stage continues to pass; the
edit plan is an additional first-class artifact, NOT a replacement.

No video compositing, no ffmpeg, no moviepy. Real rendering lands in a
later phase.
"""
from __future__ import annotations

import hashlib
import json

from common.enums import ArtifactType, StageName
from common.exceptions import StageRejection
from common.schemas import ArtifactRef, DagState, EditPlan, EditSegment, StageOutput


def _stub_uri(job_id: str, filename: str) -> str:
    return f"s3://aivideo-jobs/{job_id}/{filename}"


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

    # Existing reel_draft stub — kept so the downstream QC stage's
    # "upstream editor missing reel_draft" check stays satisfied. Real
    # compositing lands in a later phase.
    reel_draft_ref = ArtifactRef(
        artifact_type=ArtifactType.video.value,
        uri=_stub_uri(str(state.job_id), "reel_draft.mp4"),
        extra={
            "width": 1080,
            "height": 1920,
            "watermark_burned_in": False,
            "edit_plan_uri": edit_plan_ref.uri,
            "edit_plan_checksum": plan_sha,
            "phase": "phase3h_stub",
        },
    )

    return StageOutput(
        noop=False,
        notes=(
            "editor produced deterministic edit_plan from scriptwriter output; "
            "reel_draft remains a stub (no real compositing in Phase 3H)."
        ),
        artifacts={"edit_plan": edit_plan_ref, "reel_draft": reel_draft_ref},
    )
