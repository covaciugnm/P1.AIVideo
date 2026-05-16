"""Publisher — Phase 3J: QC-gated final-export manifest.

Reads the QC report (Phase 3I) and the reel_draft stub (Phase 3H), then
emits a structured ``FinalExport`` manifest as the canonical Phase 3J
output. The publisher refuses to emit if:

- the watermark / C2PA flags aren't both set (existing rule);
- the ``export_disclosure_validation`` compliance gate didn't run
  (existing rule);
- the ``qc_report`` artifact is missing from the QC stage's output;
- the ``reel_draft`` artifact is missing from the editor stage's output;
- the QC report says ``qc_passed=False``.

In all rejection cases the handler raises ``StageRejection`` — the DAG
runner moves the job to ``rejected`` and no ``final_export`` artifact
is emitted.

Phase 3J stays metadata-only. **No real video encoding** (no ffmpeg, no
moviepy, no OpenCV). **No C2PA signing** (the disclosure_status is
``"pending"``). **No external uploads** (no requests, no httpx, no
boto3). The handler keeps the legacy ``reel_final.mp4`` + ``sidecar.json``
stubs in its output so a future real-export phase can drop in real
files at the same artifact names.
"""
from __future__ import annotations

import hashlib
import json

from common.enums import ArtifactType, StageName
from common.exceptions import StageRejection
from common.schemas import ArtifactRef, DagState, FinalExport, StageOutput


def _stub_uri(job_id: str, filename: str) -> str:
    return f"s3://aivideo-jobs/{job_id}/{filename}"


def _build_final_export(
    *,
    state: DagState,
    qc_ref: ArtifactRef,
    qc_passed: bool,
    reel_draft_ref: ArtifactRef,
    export_uri: str,
) -> FinalExport:
    return FinalExport(
        passed_qc=qc_passed,
        status="published" if qc_passed else "blocked",
        job_id=str(state.job_id),
        source_reel_draft_uri=reel_draft_ref.uri,
        source_reel_draft_checksum=reel_draft_ref.checksum_sha256,
        qc_report_uri=qc_ref.uri,
        qc_report_checksum=qc_ref.checksum_sha256,
        export_uri=export_uri,
        export_type="video/mp4",
        mime_type="video/mp4",
        target_duration_seconds=float(state.target_duration_seconds),
        watermark_required=state.watermark_required,
        c2pa_required=state.c2pa_required,
        # Real C2PA signing lands in a later phase. The manifest records
        # the intended state so audit tooling can flag jobs whose
        # disclosure pipeline hasn't completed yet.
        disclosure_status="pending",
        metadata={
            "phase": "phase3j",
            "no_real_export": True,
            "no_external_upload": True,
            "expected_format": "mp4",
        },
    )


async def run(state: DagState) -> StageOutput:
    if not state.watermark_required or not state.c2pa_required:
        raise StageRejection(
            StageName.publisher.value,
            "refusing to publish without watermark_required + c2pa_required",
        )

    disclosure_output = state.stage_outputs.get(
        StageName.export_disclosure_validation.value
    )
    if disclosure_output is None:
        raise StageRejection(
            StageName.publisher.value,
            "export_disclosure_validation must run before publisher",
        )

    # Phase 3J: QC report must be present AND passing.
    qc_output = state.stage_outputs.get(StageName.qc.value)
    if qc_output is None or "qc_report" not in qc_output.artifacts:
        raise StageRejection(
            StageName.publisher.value,
            "upstream qc missing 'qc_report' artifact — refusing to publish",
        )
    qc_ref = qc_output.artifacts["qc_report"]
    qc_passed = bool(qc_ref.extra.get("qc_passed", False)) if isinstance(qc_ref.extra, dict) else False
    if not qc_passed:
        raise StageRejection(
            StageName.publisher.value,
            "qc_report.passed=False — refusing to publish",
        )

    # Phase 3J: reel_draft must be present (stub or real).
    editor_output = state.stage_outputs.get(StageName.editor.value)
    if editor_output is None or "reel_draft" not in editor_output.artifacts:
        raise StageRejection(
            StageName.publisher.value,
            "upstream editor missing 'reel_draft' artifact — refusing to publish",
        )
    reel_draft_ref = editor_output.artifacts["reel_draft"]

    # Phase 9D: the publisher still doesn't encode a real final MP4 in
    # Phase 3J semantics (real C2PA + final export lands in a later
    # phase). When the upstream reel_draft is itself a metadata-only
    # placeholder, surface that downstream by keeping the export_uri
    # honest (no fake ``reel_final.mp4`` claim).
    upstream_extra = (
        reel_draft_ref.extra if isinstance(reel_draft_ref.extra, dict) else {}
    )
    upstream_is_placeholder = upstream_extra.get("real_editor_output") is False
    if upstream_is_placeholder:
        export_uri = (
            f"placeholder://publisher/{state.job_id}/no-real-final-export"
        )
    else:
        export_uri = _stub_uri(str(state.job_id), "reel_final.mp4")

    manifest = _build_final_export(
        state=state,
        qc_ref=qc_ref,
        qc_passed=qc_passed,
        reel_draft_ref=reel_draft_ref,
        export_uri=export_uri,
    )

    manifest_json = manifest.model_dump_json()
    manifest_bytes = manifest_json.encode("utf-8")
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()

    final_export_ref = ArtifactRef(
        artifact_type=ArtifactType.final_export.value,
        # The artifact itself IS the JSON manifest. The would-be video
        # URI lives inside `final_export.export_uri` (still a stub).
        uri=_stub_uri(str(state.job_id), "final_export.json"),
        mime_type="application/json",
        checksum_sha256=manifest_sha,
        size_bytes=len(manifest_bytes),
        extra={
            "phase": "phase3j",
            "passed_qc": qc_passed,
            "status": manifest.status,
            "disclosure_status": manifest.disclosure_status,
            "final_export": json.loads(manifest_json),
        },
    )

    # Keep the legacy reel_final + sidecar stubs so a future real-export
    # phase has stable artifact names to drop into. Neither is promoted
    # to the artifacts table here (no checksum on the video stub; the
    # sidecar would be replaced by a C2PA manifest later anyway).
    reel_final_ref = ArtifactRef(
        artifact_type=ArtifactType.video.value,
        uri=export_uri,
        extra={
            "phase": (
                "phase9d_placeholder_no_real_final"
                if upstream_is_placeholder
                else "phase3j_stub"
            ),
            "real_final_export": False,
            "is_placeholder": upstream_is_placeholder,
            "upstream_reel_draft_real_editor_output": (
                upstream_extra.get("real_editor_output")
            ),
            "final_export_uri": final_export_ref.uri,
            "final_export_checksum": manifest_sha,
        },
    )
    sidecar_ref = ArtifactRef(
        artifact_type=ArtifactType.metadata.value,
        uri=_stub_uri(str(state.job_id), "sidecar.json"),
        extra={
            "phase": "phase3j_stub",
            "c2pa_present": False,
            "watermark_present": False,
            "final_export_uri": final_export_ref.uri,
        },
    )

    return StageOutput(
        noop=False,
        notes=(
            f"publisher emitted final_export manifest (passed_qc={qc_passed}, "
            "status=published); no real video encoded, no external upload"
        ),
        artifacts={
            "final_export": final_export_ref,
            "reel_final": reel_final_ref,
            "sidecar": sidecar_ref,
        },
    )
