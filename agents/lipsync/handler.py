"""LipSync — Phase 2 no-op handler.

Real lip-sync (SadTalker default; MuseTalk + Wav2Lip+GFPGAN via the
provider adapter at agents/lipsync/providers/) lands in Phase 3.

Phase 2 only:
1. Verifies the compliance_token issued by pre_lipsync_auth.
2. Validates that upstream Face + Voice produced their stub artifacts.
3. Emits a stub talking_head.mp4 reference.

No GPU is touched. No model weights are loaded. No `torch` or `diffusers`
import path is reachable from this handler.
"""
from __future__ import annotations

from common.enums import StageName
from common.exceptions import ComplianceTokenError, StageRejection
from common.schemas import ArtifactRef, DagState, StageOutput

from agents.compliance_officer.compliance_token import verify_token


def _stub_uri(job_id: str, filename: str) -> str:
    return f"s3://aivideo-jobs/{job_id}/{filename}"


async def run(
    state: DagState,
    *,
    signing_key: str,
    expected_backend: str,
) -> StageOutput:
    # Token verification first — refuse before any other work.
    if not state.compliance_token:
        raise StageRejection(
            StageName.lipsync.value,
            "missing compliance_token: pre_lipsync_auth must run first",
        )
    try:
        claims = verify_token(
            state.compliance_token,
            signing_key,
            expected_job_id=str(state.job_id),
        )
    except ComplianceTokenError as exc:
        raise StageRejection(
            StageName.lipsync.value, f"compliance_token invalid: {exc}"
        ) from exc

    if claims.allowed_lipsync_backend != expected_backend:
        raise StageRejection(
            StageName.lipsync.value,
            f"token authorizes backend={claims.allowed_lipsync_backend!r}, "
            f"runner is configured for {expected_backend!r}",
        )

    # Now validate upstream artifacts.
    voice_output = state.stage_outputs.get(StageName.voice.value)
    face_output = state.stage_outputs.get(StageName.face.value)
    if voice_output is None or "narration" not in voice_output.artifacts:
        raise StageRejection(StageName.lipsync.value, "upstream voice missing narration")
    if face_output is None or "portrait" not in face_output.artifacts:
        raise StageRejection(StageName.lipsync.value, "upstream face missing portrait")

    talking_head_ref = ArtifactRef(
        kind="video",
        uri=_stub_uri(str(state.job_id), "talking_head.mp4"),
        extra={
            "fps": 25,
            "backend": expected_backend,
            "phase": "phase2_noop",
        },
    )
    return StageOutput(
        noop=True,
        notes=f"lipsync no-op: real {expected_backend} integration lands in Phase 3",
        artifacts={"talking_head": talking_head_ref},
    )
