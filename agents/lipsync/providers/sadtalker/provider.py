"""SadTalker provider — Phase 3A stub.

Implements ``LipSyncProvider``:
- declares the required SadTalker checkpoints + the GFPGAN restorer;
- resolves ``models_root`` from ``SADTALKER_MODELS_ROOT`` (preferred) or
  ``LIPSYNC_MODELS_ROOT/sadtalker``;
- runs a fast file-existence healthcheck (no hash verification yet — that
  lands in Phase 3B alongside real inference);
- verifies the compliance token before any other work;
- raises ``ProviderNotImplementedError`` from ``synthesize()`` so Phase 3A
  cannot accidentally run real inference.

The module intentionally imports nothing from torch / diffusers /
transformers / SadTalker. Those deps land alongside the real inference
path in Phase 3B.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import ClassVar

from common.exceptions import (
    ComplianceTokenError,
    MissingAssetsError,
    ProviderNotImplementedError,
)
from common.schemas import (
    AssetSpec,
    ComplianceTokenClaims,
    ProviderHealth,
)
from common.enums import ProviderHealthStatus

from agents.compliance_officer.compliance_token import verify_token
from agents.lipsync.core.provider import (
    LipSyncProvider,
    LipSyncRequest,
    LipSyncResult,
)


def _resolve_models_root() -> Path | None:
    """SADTALKER_MODELS_ROOT wins; otherwise LIPSYNC_MODELS_ROOT/sadtalker."""
    explicit = os.environ.get("SADTALKER_MODELS_ROOT")
    if explicit:
        return Path(explicit)
    lipsync_root = os.environ.get("LIPSYNC_MODELS_ROOT")
    if lipsync_root:
        return Path(lipsync_root) / "sadtalker"
    return None


def _resolve_signing_key() -> str:
    """COMPLIANCE_SIGNING_KEY from env. Empty string is treated as unset."""
    return os.environ.get("COMPLIANCE_SIGNING_KEY", "") or ""


class SadTalkerProvider(LipSyncProvider):
    name: ClassVar[str] = "sadtalker"

    def __init__(
        self,
        *,
        models_root: Path | None = None,
        signing_key: str | None = None,
    ) -> None:
        self._models_root = models_root if models_root is not None else _resolve_models_root()
        self._signing_key = signing_key if signing_key is not None else _resolve_signing_key()

    # ------------------------------------------------------------- contract

    def required_assets(self) -> list[AssetSpec]:
        """Files SadTalker needs to load. See models/MODEL_CARDS.md for
        sha256 hashes (which Phase 3B will start verifying)."""
        return [
            AssetSpec(
                relative_path="checkpoints/mapping_00109-model.pth.tar",
                description="SadTalker audio→expression mapping checkpoint (109)",
                license_note="Apache-2.0 (verify at integration time)",
            ),
            AssetSpec(
                relative_path="checkpoints/mapping_00229-model.pth.tar",
                description="SadTalker audio→expression mapping checkpoint (229)",
                license_note="Apache-2.0",
            ),
            AssetSpec(
                relative_path="checkpoints/SadTalker_V0.0.2_256.safetensors",
                description="SadTalker 256px generator weights",
                license_note="Apache-2.0",
            ),
            AssetSpec(
                relative_path="checkpoints/SadTalker_V0.0.2_512.safetensors",
                description="SadTalker 512px generator weights",
                license_note="Apache-2.0",
            ),
            AssetSpec(
                relative_path="gfpgan/GFPGANv1.4.pth",
                description="GFPGAN face-restoration weights (post-process pass)",
                license_note="Apache-2.0 (GFPGAN — check ARCSoft clause)",
            ),
        ]

    def healthcheck(self) -> ProviderHealth:
        if self._models_root is None:
            return ProviderHealth(
                backend=self.name,
                status=ProviderHealthStatus.not_configured,
                errors=[
                    "Neither SADTALKER_MODELS_ROOT nor LIPSYNC_MODELS_ROOT is set. "
                    "Set one in .env (see docs/runbooks/model-management.md)."
                ],
            )
        if not self._models_root.exists():
            return ProviderHealth(
                backend=self.name,
                status=ProviderHealthStatus.missing_assets,
                models_root=str(self._models_root),
                missing_assets=[a.relative_path for a in self.required_assets()],
                errors=[f"models_root does not exist on disk: {self._models_root}"],
            )
        missing = [
            a.relative_path
            for a in self.required_assets()
            if not (self._models_root / a.relative_path).is_file()
        ]
        if missing:
            return ProviderHealth(
                backend=self.name,
                status=ProviderHealthStatus.missing_assets,
                models_root=str(self._models_root),
                missing_assets=missing,
                errors=[
                    f"{len(missing)} required SadTalker asset(s) missing under "
                    f"{self._models_root}; place them manually (no auto-download)."
                ],
            )
        return ProviderHealth(
            backend=self.name,
            status=ProviderHealthStatus.ok,
            models_root=str(self._models_root),
            extra={"phase": "3a_stub", "real_inference": False},
        )

    def validate_compliance_token(
        self,
        token: str,
        *,
        expected_job_id: str,
    ) -> ComplianceTokenClaims:
        if not self._signing_key:
            # No signing key configured: every token would verify against
            # an empty secret. Refuse explicitly rather than silently
            # accept anything.
            raise ComplianceTokenError(
                "COMPLIANCE_SIGNING_KEY not configured; refusing to validate tokens"
            )
        return verify_token(token, self._signing_key, expected_job_id=expected_job_id)

    async def synthesize(self, req: LipSyncRequest) -> LipSyncResult:
        """Phase 3A fail-fast synthesize.

        Order matters: validate the compliance token FIRST so a bad token
        never sees any provider state, then enforce asset presence, then
        explicitly refuse to proceed to inference.
        """
        # 1. Token first.
        self.validate_compliance_token(
            req.compliance_token, expected_job_id=str(req.job_id)
        )

        # 2. Assets must be present.
        health = self.healthcheck()
        if health.status is not ProviderHealthStatus.ok:
            raise MissingAssetsError(self.name, health.missing_assets)

        # 3. Phase 3A never runs real inference.
        raise ProviderNotImplementedError(
            "sadtalker: real inference lands in Phase 3B; "
            "Phase 3A only validates the contract + assets."
        )
