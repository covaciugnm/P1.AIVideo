"""MuseTalk provider — placeholder (planned for v2).

This module exists so the registry can resolve ``LIPSYNC_BACKEND=musetalk``
to a real Python class today, but it does not implement real inference.

When Phase 3B (or later) reaches MuseTalk:
- Replace ``required_assets()`` with the verified asset list (filenames +
  sha256) from the upstream repo and ``models/MODEL_CARDS.md``.
- Replace ``healthcheck()`` with the SadTalker-style on-disk check.
- Implement ``synthesize()`` against the MuseTalk inference path.
- Add the MuseTalk runtime deps (torch, …) to an ``agents`` pyproject
  extra such as ``[project.optional-dependencies] musetalk = [...]``
  rather than to the default deps.
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


class MuseTalkProvider(LipSyncProvider):
    name: ClassVar[str] = "musetalk"

    def required_assets(self) -> list[AssetSpec]:
        # Documented now so operators know what they'd need to mount in
        # the future. Real list + sha256s land in models/MODEL_CARDS.md
        # when the provider becomes runnable.
        return [
            AssetSpec(
                relative_path="checkpoints/musetalk.json",
                description="MuseTalk config (placeholder filename — verify upstream)",
                license_note="TBD (review before enabling)",
            ),
            AssetSpec(
                relative_path="checkpoints/musetalk.bin",
                description="MuseTalk model weights (placeholder filename — verify upstream)",
                license_note="TBD (review before enabling)",
            ),
        ]

    def healthcheck(self) -> ProviderHealth:
        return ProviderHealth(
            backend=self.name,
            status=ProviderHealthStatus.not_implemented,
            errors=[
                "musetalk: placeholder provider; planned for v2. "
                "Real implementation deferred to Phase 3B+. "
                "See docs/architecture/lipsync-adapter.md."
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
            "musetalk: validate_compliance_token not implemented (Phase 3B+)"
        )

    async def synthesize(self, req: LipSyncRequest) -> LipSyncResult:
        raise ProviderNotImplementedError(
            "musetalk: synthesize not implemented (Phase 3B+); "
            "see docs/architecture/lipsync-adapter.md for the upgrade path."
        )
