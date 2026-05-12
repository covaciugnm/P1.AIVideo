"""Face — Phase 2 no-op handler.

Real synthetic-portrait generation (SDXL + persona LoRA, with the negative
prompt enforcing "no real person/celebrity/identifiable likeness") lands
in Phase 3. Phase 2 only emits a stub portrait reference so the downstream
identity_guard stage has something to read.

The identity_guard stage in Phase 2 is also a no-op; the real CLIP-NN
check against the public-figures index lands in Phase 5.
"""
from __future__ import annotations

from common.enums import StageName
from common.exceptions import StageRejection
from common.schemas import ArtifactRef, DagState, StageOutput


def _stub_uri(job_id: str, filename: str) -> str:
    return f"s3://aivideo-jobs/{job_id}/{filename}"


async def run(state: DagState) -> StageOutput:
    if not state.synthetic_person_confirmed:
        # Defensive: the API + policy_gate already enforce this; we re-check
        # because the face stage is the one that would produce likeness.
        raise StageRejection(StageName.face.value, "synthetic_person_confirmed must be true")

    portrait_ref = ArtifactRef(
        kind="image",
        uri=_stub_uri(str(state.job_id), "portrait.png"),
        extra={
            "synthetic": True,
            "phase": "phase2_noop",
        },
    )
    return StageOutput(
        noop=True,
        notes="face no-op: real SDXL + persona LoRA lands in Phase 3",
        artifacts={"portrait": portrait_ref},
    )
