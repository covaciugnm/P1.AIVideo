"""Voice provider contract.

Mirrors the LipSync adapter pattern: a thin abstract base + a registry, so
the orchestrator stays decoupled from any specific TTS backend.

Phase 3A scope:
- ABC + request / result types.
- Piper stub that declares the ``.onnx`` and ``.json`` files it needs,
  resolves ``models_root`` from env, runs an on-disk healthcheck, and
  raises ``ProviderNotImplementedError`` from synthesize.

Voice does NOT need a compliance token in Phase 3A — TTS doesn't gate on
synthetic-person checks the way LipSync does. The voice-cloning guard
(no real-voice cloning, ever) is enforced at packaging time: this module
will never import a cloning-capable code path.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from common.schemas import AssetSpec, ProviderHealth


class VoiceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: uuid.UUID
    text: str                       # plain text or SSML; provider-specific
    voice_id: str                   # references configs/voices/<id>.yaml
    sample_rate: int = 48000
    params: dict[str, Any] = Field(default_factory=dict)


class VoiceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    narration_uri: str              # MinIO URI for the produced narration.wav
    phonemes_uri: str | None = None
    duration_ms: int
    sample_rate: int
    model_version: str
    voice_id: str


class VoiceProvider(ABC):
    name: ClassVar[str] = ""

    @abstractmethod
    def required_assets(self) -> list[AssetSpec]:
        """Files the provider needs at load time (e.g. Piper ``.onnx`` + ``.json``)."""

    @abstractmethod
    def healthcheck(self) -> ProviderHealth:
        """Structured status: ok / missing_assets / not_configured / ..."""

    @abstractmethod
    async def synthesize(self, req: VoiceRequest) -> VoiceResult:
        """Phase 3A providers fail fast: refuse if assets missing, then
        raise ``ProviderNotImplementedError``. Real inference in Phase 3B."""
