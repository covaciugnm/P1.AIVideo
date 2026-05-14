"""QC — Phase 3I: structured QC report from upstream metadata artifacts.

Phase 3I scope: validate the SHAPE of the artifact graph produced so
far, not real media content. Specifically, the QC stage:

1. Pulls the ``edit_plan`` + ``reel_draft`` artifacts from the editor
   stage's output and the ``script`` artifact from the scriptwriter
   stage's output. If any required artifact reference is missing, the
   stage rejects (this is a wiring failure, not a content failure).
2. Runs four structural checks against the artifacts:
   - ``script_artifact_present``  — the script ref exists and carries
     a checksum.
   - ``segments_present``         — the edit_plan has the three
     expected segment types in the expected order.
   - ``total_duration_matches_target`` — segment durations sum to the
     declared ``target_duration_seconds`` (compared in ms, 1 ms
     tolerance).
   - ``reel_draft_is_stub``       — the reel_draft is still a Phase 3H
     metadata stub (``s3://`` URI, no ``local_path``). Real-media QC
     will replace this check in a later phase.
3. Emits a ``QCReport`` artifact (``ArtifactType.metadata``,
   ``application/json``) with a content checksum so it lands in the
   ``artifacts`` table for downstream stages.

No ffmpeg, no ffprobe, no mediainfo, no real file reads.
"""
from __future__ import annotations

import hashlib
import json

from common.enums import ArtifactType, StageName
from common.exceptions import StageRejection
from common.schemas import ArtifactRef, DagState, QCCheck, QCReport, StageOutput


_EXPECTED_SEGMENTS = ["hook", "body", "cta"]
_DURATION_TOLERANCE_MS = 1  # generous; mismatches mean real bugs


def _stub_uri(job_id: str, filename: str) -> str:
    return f"s3://aivideo-jobs/{job_id}/{filename}"


def _check_script_artifact(script_ref: ArtifactRef) -> QCCheck:
    if not script_ref.checksum_sha256:
        return QCCheck(
            name="script_artifact_present",
            decision="fail",
            detail="script artifact lacks a content checksum",
        )
    return QCCheck(
        name="script_artifact_present",
        decision="pass",
        detail=f"script artifact has checksum {script_ref.checksum_sha256[:12]}...",
    )


def _check_segments(plan_dict: dict) -> QCCheck:
    segments = plan_dict.get("segments") if isinstance(plan_dict, dict) else None
    if not isinstance(segments, list) or not segments:
        return QCCheck(
            name="segments_present",
            decision="fail",
            detail="edit_plan has no segments",
        )
    types = [s.get("segment_type") for s in segments if isinstance(s, dict)]
    if types != _EXPECTED_SEGMENTS:
        return QCCheck(
            name="segments_present",
            decision="fail",
            detail=f"expected segment types {_EXPECTED_SEGMENTS}; got {types}",
            metadata={"actual_segment_types": types},
        )
    return QCCheck(
        name="segments_present",
        decision="pass",
        detail=f"three segments present in order: {types}",
    )


def _check_total_duration(plan_dict: dict, target_seconds: float) -> QCCheck:
    target_ms = round(target_seconds * 1000)
    segments = plan_dict.get("segments") if isinstance(plan_dict, dict) else None
    if not isinstance(segments, list):
        return QCCheck(
            name="total_duration_matches_target",
            decision="fail",
            detail="edit_plan has no segments to total",
        )
    total_ms = 0
    for s in segments:
        if not isinstance(s, dict):
            continue
        dur = s.get("duration_seconds")
        if isinstance(dur, (int, float)):
            total_ms += round(dur * 1000)
    if abs(total_ms - target_ms) > _DURATION_TOLERANCE_MS:
        return QCCheck(
            name="total_duration_matches_target",
            decision="fail",
            detail=f"segments sum to {total_ms} ms; target is {target_ms} ms",
            metadata={"total_ms": total_ms, "target_ms": target_ms},
        )
    return QCCheck(
        name="total_duration_matches_target",
        decision="pass",
        detail=f"segments sum to {total_ms} ms (target {target_ms} ms)",
    )


def _check_reel_draft_stub(reel_draft_ref: ArtifactRef) -> QCCheck:
    if reel_draft_ref.local_path:
        return QCCheck(
            name="reel_draft_is_stub",
            decision="warn",
            detail=(
                "reel_draft carries a local_path — real-media QC would "
                "inspect the file; Phase 3I does not."
            ),
        )
    if not reel_draft_ref.uri.startswith("s3://"):
        return QCCheck(
            name="reel_draft_is_stub",
            decision="warn",
            detail=f"reel_draft URI {reel_draft_ref.uri!r} is not the expected s3:// stub",
        )
    return QCCheck(
        name="reel_draft_is_stub",
        decision="pass",
        detail="reel_draft remains a metadata stub (expected in Phase 3I)",
    )


async def run(state: DagState) -> StageOutput:
    editor_output = state.stage_outputs.get(StageName.editor.value)
    if editor_output is None:
        raise StageRejection(StageName.qc.value, "upstream editor stage produced no output")

    edit_plan_ref = editor_output.artifacts.get("edit_plan")
    if edit_plan_ref is None:
        raise StageRejection(
            StageName.qc.value, "upstream editor missing 'edit_plan' artifact"
        )
    reel_draft_ref = editor_output.artifacts.get("reel_draft")
    if reel_draft_ref is None:
        raise StageRejection(
            StageName.qc.value, "upstream editor missing 'reel_draft' artifact"
        )

    script_output = state.stage_outputs.get(StageName.scriptwriter.value)
    if script_output is None or "script" not in script_output.artifacts:
        raise StageRejection(
            StageName.qc.value, "upstream scriptwriter missing 'script' artifact"
        )
    script_ref = script_output.artifacts["script"]

    plan_dict = edit_plan_ref.extra.get("edit_plan") if isinstance(edit_plan_ref.extra, dict) else None
    if not isinstance(plan_dict, dict):
        plan_dict = {}

    target = float(state.target_duration_seconds)

    checks: list[QCCheck] = [
        _check_script_artifact(script_ref),
        _check_segments(plan_dict),
        _check_total_duration(plan_dict, target),
        _check_reel_draft_stub(reel_draft_ref),
    ]
    passed = all(c.decision == "pass" for c in checks)

    segments = plan_dict.get("segments") if isinstance(plan_dict.get("segments"), list) else []
    report = QCReport(
        passed=passed,
        checks=checks,
        script_artifact_uri=script_ref.uri,
        script_artifact_checksum=script_ref.checksum_sha256,
        edit_plan_artifact_uri=edit_plan_ref.uri,
        edit_plan_artifact_checksum=edit_plan_ref.checksum_sha256,
        reel_draft_artifact_uri=reel_draft_ref.uri,
        target_duration_seconds=target,
        segment_count=len(segments),
        expected_segments=list(_EXPECTED_SEGMENTS),
        metadata={
            "phase": "phase3i",
            "checks_run": [c.name for c in checks],
            "real_media_inspected": False,
        },
    )

    report_json = report.model_dump_json()
    report_bytes = report_json.encode("utf-8")
    report_sha = hashlib.sha256(report_bytes).hexdigest()

    qc_report_ref = ArtifactRef(
        artifact_type=ArtifactType.metadata.value,
        uri=_stub_uri(str(state.job_id), "qc_report.json"),
        mime_type="application/json",
        checksum_sha256=report_sha,
        size_bytes=len(report_bytes),
        extra={
            "phase": "phase3i",
            "qc_passed": passed,
            "check_count": len(checks),
            "qc_report": json.loads(report_json),
        },
    )

    return StageOutput(
        noop=False,
        notes=(
            f"qc produced structured QC report "
            f"({len(checks)} checks, passed={passed}); no real media inspected"
        ),
        artifacts={"qc_report": qc_report_ref},
    )
