"""LipSync provider contract.

Every lip-sync backend (SadTalker default; MuseTalk v2; Wav2Lip fallback)
implements ``LipSyncProvider``. The orchestrator never imports a concrete
provider — it resolves one through ``agents.lipsync.core.registry``.

Phase 3A scope:
- Define the ABC + request/result types.
- Ship a SadTalker implementation that declares its required assets, runs
  a structured healthcheck, validates the compliance token, and **fails
  fast** on synthesize: it does NOT call real SadTalker inference.
- MuseTalk and Wav2Lip are placeholder implementations that report
  ``not_implemented`` and raise ``ProviderNotImplementedError`` from
  synthesize.

Real inference lands in Phase 3B (per-provider).
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from common.schemas import AssetSpec, ComplianceTokenClaims, ProviderHealth


class LipSyncRequest(BaseModel):
    """Input envelope to ``LipSyncProvider.synthesize()``.

    All media is passed by *reference* (URIs), never as bytes. The DAG
    runner constructs this from ``DagState`` (Phase 3B will wire that up;
    Phase 3A only uses it in tests).
    """

    model_config = ConfigDict(extra="forbid")

    job_id: uuid.UUID
    portrait_uri: str           # MinIO / S3 URI to the synthetic portrait
    audio_uri: str              # MinIO / S3 URI to narration.wav
    phonemes_uri: str | None = None
    fps: int = 25
    seed: int = 0
    compliance_token: str       # JWT-like string minted by pre_lipsync_auth
    params: dict[str, Any] = Field(default_factory=dict)


class LipSyncResult(BaseModel):
    """Return shape from a successful ``synthesize()``.

    Phase 3A providers never reach this — the fail-fast checks always
    raise. Defined now so Phase 3B implementations have a stable contract.
    """

    model_config = ConfigDict(extra="forbid")

    video_uri: str
    frame_count: int
    sync_score: float
    model_version: str
    seed_used: int
    duration_ms: int


class LipSyncProvider(ABC):
    """Abstract base for lip-sync backends.

    Subclasses must set the class attribute ``name`` to a stable string id
    (used by the registry and by ``LIPSYNC_BACKEND``).
    """

    name: ClassVar[str] = ""

    @abstractmethod
    def required_assets(self) -> list[AssetSpec]:
        """Declare every file the provider needs at load time.

        Paths are relative to the provider's ``models_root``. Operators are
        responsible for placing these files on disk; nothing is downloaded
        automatically (see ``ALLOW_MODEL_AUTODOWNLOAD`` in ``.env.example``
        — Phase 3A does NOT honor it).
        """

    @abstractmethod
    def healthcheck(self) -> ProviderHealth:
        """Return a structured status: ok / missing_assets / not_configured / ..."""

    @abstractmethod
    def validate_compliance_token(
        self,
        token: str,
        *,
        expected_job_id: str,
    ) -> ComplianceTokenClaims:
        """Verify the token before any other work.

        Implementations must raise ``ComplianceTokenError`` on:
        - missing / empty token
        - bad signature
        - expired token
        - job_id mismatch
        """

    @abstractmethod
    async def synthesize(self, req: LipSyncRequest) -> LipSyncResult:
        """Run lip-sync. Phase 3A providers MUST fail fast: token check
        first, then asset check, then raise ``ProviderNotImplementedError``
        (the real inference path lands in Phase 3B)."""
