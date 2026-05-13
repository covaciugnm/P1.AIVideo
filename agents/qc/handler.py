"""QC — Phase 2 no-op handler.

Real QC (sync confidence, face stability, NSFW scan, transcript re-scan,
OCR for disclosure overlay, identity-guard sampling, C2PA verify) lands
in Phase 6. Phase 2 only emits a stub qc_report.json reference with a
trivially-passing result.
"""
from __future__ import annotations

from common.enums import StageName
from common.exceptions import StageRejection
from common.schemas import ArtifactRef, DagState, StageOutput


def _stub_uri(job_id: str, filename: str) -> str:
    return f"s3://aivideo-jobs/{job_id}/{filename}"


async def run(state: DagState) -> StageOutput:
    reel_draft_output = state.stage_outputs.get(StageName.editor.value)
    if reel_draft_output is None or "reel_draft" not in reel_draft_output.artifacts:
        raise StageRejection(StageName.qc.value, "upstream editor missing reel_draft")

    qc_report_ref = ArtifactRef(
        artifact_type="json",
        uri=_stub_uri(str(state.job_id), "qc_report.json"),
        extra={
            "result": "pass",
            "checks": {"phase2_noop": True},
            "phase": "phase2_noop",
        },
    )
    return StageOutput(
        noop=True,
        notes="qc no-op: real checks land in Phase 6",
        artifacts={"qc_report": qc_report_ref},
    )
