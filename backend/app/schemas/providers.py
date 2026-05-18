"""Provider-selection schemas.

Phase 4F: per-job provider selection (LLM / TTS / video).
Phase 6D: hardened multi-category registry — adds ``audio_processor`` and
``image_processor`` categories, plus richer ``ProviderInfo`` metadata
(local_or_external, requires_network, requires_gpu, requires_model_files,
supported_models, healthcheck_available, warning, docs_url, is_custom).

Backward compatibility: every new ``ProviderInfo`` field is optional /
defaulted, so older clients that only read the Phase 4F shape keep
working unchanged. The two new categories are additive in
``ProvidersResponse``; older callers that only inspect the three
original keys are unaffected.

Provider IDs are not validated against the catalog at job-create time
— jobs can carry forward-looking provider IDs for future-phase
runtimes, and runtime endpoints surface a clean ``not_configured`` /
``not_implemented`` / ``unknown_provider`` instead of rejecting at
write time.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Provider categories. Phase 6D added ``audio_processor`` /
# ``image_processor``; Phase 12 adds ``image_generator`` (FLUX / SD3.5
# / hosted-API backends used by the Characters tab). Older clients that
# don't know about new keys simply ignore them on the catalog response.
ProviderCategory = Literal[
    "llm",
    "tts",
    "video_generator",
    "audio_processor",
    "image_processor",
    "image_generator",
]


ProviderLocality = Literal["local", "external"]
ProviderStatusValue = Literal[
    "available",
    "configured",
    "not_configured",
    "not_implemented",
    "disabled",
    "error",
]


class ProviderSelection(BaseModel):
    """Per-job provider/tool selection.

    Every field is optional. Unknown provider IDs are accepted at
    write time (the runtime is the gate); ``extra="forbid"`` only
    rejects unknown *keys*. Phase 6D adds ``audio_processor_id`` and
    ``image_processor_id``.
    """

    model_config = ConfigDict(extra="forbid")

    script_provider_id: str | None = Field(default=None, max_length=80)
    script_model: str | None = Field(default=None, max_length=160)
    tts_provider_id: str | None = Field(default=None, max_length=80)
    tts_model: str | None = Field(default=None, max_length=160)
    video_provider_id: str | None = Field(default=None, max_length=80)
    video_model: str | None = Field(default=None, max_length=160)
    # Phase 6D additions.
    audio_processor_id: str | None = Field(default=None, max_length=80)
    image_processor_id: str | None = Field(default=None, max_length=80)
    # Phase 12 — text-to-image / image-to-image generation backend
    # (FLUX local default, BFL API, SD3.5, hosted APIs, mock).
    image_generator_id: str | None = Field(default=None, max_length=80)
    image_generator_model: str | None = Field(default=None, max_length=160)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class ProviderInfo(BaseModel):
    """One provider returned by /api/v1/providers/*.

    Phase 6D additions are all optional with safe defaults so older
    clients keep working. ``is_local`` is retained for backward compat
    and mirrors ``local_or_external``.
    """

    model_config = ConfigDict(extra="forbid")

    category: ProviderCategory
    provider_id: str
    label: str
    backend_type: str
    default_model: str | None = None
    is_local: bool = True
    status: ProviderStatusValue
    notes: str = ""
    # Phase 6D additions.
    local_or_external: ProviderLocality = "local"
    supported_models: list[str] = Field(default_factory=list)
    requires_network: bool = False
    requires_gpu: bool = False
    requires_model_files: bool = False
    healthcheck_available: bool = False
    warning: str = ""
    docs_url: str = ""
    is_custom: bool = False


class ProvidersResponse(BaseModel):
    """The top-level /api/v1/providers payload.

    The two Phase 6D categories carry safe defaults so older test
    fixtures (or older clients) that only enumerate the three original
    keys still pass equality / subset checks.
    """

    model_config = ConfigDict(extra="forbid")

    llm: list[ProviderInfo]
    tts: list[ProviderInfo]
    video_generator: list[ProviderInfo]
    # Phase 6D additions.
    audio_processor: list[ProviderInfo] = Field(default_factory=list)
    image_processor: list[ProviderInfo] = Field(default_factory=list)
    # Phase 12 — image generation backends (Characters tab).
    image_generator: list[ProviderInfo] = Field(default_factory=list)
