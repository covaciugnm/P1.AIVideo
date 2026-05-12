"""Wav2Lip + GFPGAN provider — placeholder (rapid-fallback tier).

Intended for low-VRAM hosts or speed-critical jobs once Phase 3B is
shipped. Phase 3A only registers the class so the registry can resolve
``LIPSYNC_BACKEND=wav2lip``.

License caveat: the original Wav2Lip checkpoints carry NON-COMMERCIAL
terms. Do NOT enable this provider for commercial deployments without
sourcing alternative permissive weights and updating
``models/MODEL_CARDS.md``.
"""
from __future__ import annotations

from typing import ClassVar

from common.exceptions import ProviderNotImplementedError
from common.enums import ProviderHealthStatus
from common.schemas import AssetSpec, ComplianceTokenClaims, ProviderHealth

from agents.lipsync.core.provider import (
    LipSyncProvider,
    LipSyncRequest,
    LipSyncResult,
)


class Wav2LipProvider(LipSyncProvider):
    name: ClassVar[str] = "wav2lip"

    def required_assets(self) -> list[AssetSpec]:
        return [
            AssetSpec(
                relative_path="checkpoints/wav2lip_gan.pth",
                description="Wav2Lip GAN weights (placeholder — verify license before use)",
                license_note=(
                    "Wav2Lip original checkpoints: NON-COMMERCIAL. "
                    "Do not enable in commercial deployments without permissive replacement."
                ),
            ),
            AssetSpec(
                relative_path="checkpoints/face_detection_yunet.onnx",
                description="Face detector (placeholder — verify license)",
                license_note="TBD",
            ),
            AssetSpec(
                relative_path="gfpgan/GFPGANv1.4.pth",
                description="GFPGAN restoration weights",
                license_note="Apache-2.0 (ARCSoft clause; review)",
            ),
        ]

    def healthcheck(self) -> ProviderHealth:
        return ProviderHealth(
            backend=self.name,
            status=ProviderHealthStatus.not_implemented,
            errors=[
                "wav2lip: placeholder provider; planned as fallback tier. "
                "Real implementation deferred to Phase 3B+. "
                "License posture (non-commercial original weights) must be "
                "reconciled before commercial enablement."
            ],
            extra={"planned_phase": "3B+"},
        )

    def validate_compliance_token(
        self,
        token: str,
        *,
        expected_job_id: str,
    ) -> ComplianceTokenClaims:
        raise ProviderNotImplementedError(
            "wav2lip: validate_compliance_token not implemented (Phase 3B+)"
        )

    async def synthesize(self, req: LipSyncRequest) -> LipSyncResult:
        raise ProviderNotImplementedError(
            "wav2lip: synthesize not implemented (Phase 3B+); "
            "see docs/architecture/lipsync-adapter.md."
        )
