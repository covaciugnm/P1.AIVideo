"""Provider-selection schemas (Phase 4F).

These describe what the operator picks per-job for LLM script generation,
TTS, and video generation. They're metadata-only: every field is optional,
unknown providers don't cause job rejection — the orchestrator simply
falls back to its configured default or emits ``provider_not_configured``
when generation is requested.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ProviderCategory = Literal["llm", "tts", "video_generator"]


class ProviderSelection(BaseModel):
    """Per-job selection. Every field optional + extra forbidden.

    The string IDs are validated only at the syntactic level (length + a
    permissive alphabet) — we don't reject unknown providers here, since
    the providers catalog is operator-extensible.
    """

    model_config = ConfigDict(extra="forbid")

    script_provider_id: str | None = Field(default=None, max_length=80)
    script_model: str | None = Field(default=None, max_length=160)
    tts_provider_id: str | None = Field(default=None, max_length=80)
    tts_model: str | None = Field(default=None, max_length=160)
    video_provider_id: str | None = Field(default=None, max_length=80)
    video_model: str | None = Field(default=None, max_length=160)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class ProviderInfo(BaseModel):
    """One provider returned by /api/v1/providers/*."""

    model_config = ConfigDict(extra="forbid")

    category: ProviderCategory
    provider_id: str
    label: str
    backend_type: str
    default_model: str | None = None
    is_local: bool = True
    status: Literal[
        "available",
        "configured",
        "not_configured",
        "not_implemented",
        "disabled",
    ]
    notes: str = ""


class ProvidersResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm: list[ProviderInfo]
    tts: list[ProviderInfo]
    video_generator: list[ProviderInfo]
