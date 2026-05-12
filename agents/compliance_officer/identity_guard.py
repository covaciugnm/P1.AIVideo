"""identity_guard — no-op for Phase 2.

The real identity guard (CLIP-NN against a public-figures embedding index)
is documented in docs/compliance/identity-guard.md and lands in Phase 5
alongside the real Face agent. Phase 2 only validates metadata — that a
portrait artifact reference exists in the state — and accepts.

This is **not** a security shortcut: Phase 2 doesn't generate real faces,
so there's nothing to guard. When real face generation lands, this stage
must be replaced (not bypassed).
"""
from __future__ import annotations

from common.enums import StageName
from common.exceptions import StageRejection
from common.schemas import ArtifactRef, DagState, StageOutput


async def run(state: DagState) -> StageOutput:
    face_output = state.stage_outputs.get(StageName.face.value)
    if face_output is None or "portrait" not in face_output.artifacts:
        raise StageRejection(
            stage=StageName.identity_guard.value,
            reason="identity_guard: no portrait artifact found from upstream face stage",
        )

    portrait_ref: ArtifactRef = face_output.artifacts["portrait"]
    return StageOutput(
        noop=True,
        notes="identity_guard accepts (no-op): real CLIP-NN check lands in Phase 5",
        extra={
            "decision": "accept",
            "reviewed_portrait_uri": portrait_ref.uri,
        },
    )
