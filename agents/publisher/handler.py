"""Publisher — Phase 2 no-op handler.

Real publishing (C2PA sign via c2patool, XMP/EXIF flags via exiftool,
perceptual hash, sidecar.json) lands in Phase 5. Phase 2 only emits stub
references for the final reel + sidecar.

The handler still enforces the production guard: refuses to emit if
watermark or C2PA flags aren't set. This matches the hard rule documented
in docs/compliance/disclosure.md.
"""
from __future__ import annotations

from common.enums import StageName
from common.exceptions import StageRejection
from common.schemas import ArtifactRef, DagState, StageOutput


def _stub_uri(job_id: str, filename: str) -> str:
    return f"s3://aivideo-jobs/{job_id}/{filename}"


async def run(state: DagState) -> StageOutput:
    if not state.watermark_required or not state.c2pa_required:
        raise StageRejection(
            StageName.publisher.value,
            "refusing to publish without watermark_required + c2pa_required",
        )

    disclosure_output = state.stage_outputs.get(StageName.export_disclosure_validation.value)
    if disclosure_output is None:
        raise StageRejection(
            StageName.publisher.value,
            "export_disclosure_validation must run before publisher",
        )

    reel_final_ref = ArtifactRef(
        artifact_type="video",
        uri=_stub_uri(str(state.job_id), "reel_final.mp4"),
        extra={"phase": "phase2_noop"},
    )
    sidecar_ref = ArtifactRef(
        artifact_type="json",
        uri=_stub_uri(str(state.job_id), "sidecar.json"),
        extra={
            "c2pa_present": False,  # noop — would be True after Phase 5
            "watermark_present": False,  # noop
            "phase": "phase2_noop",
        },
    )
    return StageOutput(
        noop=True,
        notes="publisher no-op: real C2PA signing + XMP labelling lands in Phase 5",
        artifacts={"reel_final": reel_final_ref, "sidecar": sidecar_ref},
    )
