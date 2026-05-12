"""pre_lipsync_auth — issues the compliance_token consumed by LipSync.

This is the ONLY place a valid compliance_token is minted. LipSync rejects
any request whose token wasn't issued here.

Phase 2: HMAC-signed envelope using `COMPLIANCE_SIGNING_KEY` from settings.
Phase 5+: may upgrade to asymmetric (JWT/RSA) signing.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from common.enums import StageName
from common.exceptions import StageRejection
from common.schemas import ComplianceTokenClaims, DagState, StageOutput

from agents.compliance_officer.compliance_token import mint_token


async def run(
    state: DagState,
    *,
    signing_key: str,
    allowed_lipsync_backend: str,
    token_ttl_seconds: int = 3600,
) -> StageOutput:
    # Defense in depth: a token is only valid if upstream compliance signals
    # are clean. The runner already aborted on rejection, so reaching this
    # stage means policy_gate + identity_guard accepted — but we re-check
    # the load-bearing flags directly from state in case a future runner
    # changes order.
    if not state.synthetic_person_confirmed:
        raise StageRejection(
            StageName.pre_lipsync_auth.value, "synthetic_person_confirmed must be true"
        )
    if not state.consent_confirmed:
        raise StageRejection(
            StageName.pre_lipsync_auth.value, "consent_confirmed must be true"
        )
    if not state.watermark_required:
        raise StageRejection(
            StageName.pre_lipsync_auth.value, "watermark_required must be true"
        )
    if not state.c2pa_required:
        raise StageRejection(
            StageName.pre_lipsync_auth.value, "c2pa_required must be true"
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expires = now + timedelta(seconds=token_ttl_seconds)
    claims = ComplianceTokenClaims(
        job_id=str(state.job_id),
        synthetic_person_confirmed=state.synthetic_person_confirmed,
        consent_confirmed=state.consent_confirmed,
        watermark_required=state.watermark_required,
        c2pa_required=state.c2pa_required,
        allowed_lipsync_backend=allowed_lipsync_backend,
        issued_at=now,
        expires_at=expires,
        phase="phase2_noop",
        issued_by="pre_lipsync_auth",
    )
    token = mint_token(claims, signing_key)

    return StageOutput(
        noop=True,
        notes="pre_lipsync_auth minted compliance_token",
        extra={
            "compliance_token": token,
            "issued_at": claims.issued_at.isoformat(),
            "expires_at": claims.expires_at.isoformat(),
            "allowed_lipsync_backend": allowed_lipsync_backend,
        },
    )
