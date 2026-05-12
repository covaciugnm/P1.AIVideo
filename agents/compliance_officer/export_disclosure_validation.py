"""export_disclosure_validation — pre-publish compliance attestation.

Phase 2 is metadata-only: there is no real reel to OCR, so this stage just
confirms that the QC stage produced a report and that the watermark+C2PA
flags are still set. Real disclosure validation (OCR for the burned-in
overlay, C2PA manifest verify, identity-guard sampling) lands in Phase 5
alongside the real Editor + Publisher.

The Publisher refuses to emit without this stage having succeeded.
"""
from __future__ import annotations

from common.enums import StageName
from common.exceptions import StageRejection
from common.schemas import DagState, StageOutput


async def run(state: DagState) -> StageOutput:
    if not state.watermark_required:
        raise StageRejection(
            StageName.export_disclosure_validation.value,
            "watermark_required is false; refusing to validate disclosure",
        )
    if not state.c2pa_required:
        raise StageRejection(
            StageName.export_disclosure_validation.value,
            "c2pa_required is false; refusing to validate disclosure",
        )

    qc_output = state.stage_outputs.get(StageName.qc.value)
    if qc_output is None:
        raise StageRejection(
            StageName.export_disclosure_validation.value, "QC report missing upstream"
        )

    return StageOutput(
        noop=True,
        notes="export_disclosure_validation accepts (no-op): real OCR/C2PA verify in Phase 5",
        extra={
            "decision": "accept",
            "watermark_required": state.watermark_required,
            "c2pa_required": state.c2pa_required,
        },
    )
