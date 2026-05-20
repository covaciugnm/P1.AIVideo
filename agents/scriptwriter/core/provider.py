"""Scriptwriter provider contract.

Phase 3G defines the abstract contract that every scriptwriter backend
implements. The orchestrator never imports a concrete provider — it
resolves one via ``agents.scriptwriter.core.registry`` based on the
``SCRIPTWRITER_BACKEND`` configuration.

Phase 3G ships exactly one functional provider — ``template`` — which
produces deterministic structured scripts without calling any LLM. Every
other registered backend (``ollama``, ``vllm``, ``openai_compatible``,
``openai``, ``anthropic``, ``local_http``) ships as a contract-only
stub: its ``healthcheck()`` returns ``not_configured`` /
``not_implemented`` and its ``generate()`` raises
``ProviderNotImplementedError``. None of the stubs import a real LLM
client at module load — that import happens lazily inside a future
``generate()`` and is gated by ``SCRIPTWRITER_ENABLE_NETWORK_CALLS``.

A future phase will activate one or more real backends. The contract
here is deliberately minimal so adding a new provider requires only:

1. A new subdirectory under ``agents/scriptwriter/providers/<name>/``
   with a ``provider.py`` implementing ``ScriptProvider``.
2. A registry entry in ``core/registry.py``.
3. (Optionally) a new block in ``configs/llm/providers.example.yaml``.

No DAG or backend changes should be required to add a model.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from common.schemas import ProviderHealth


class ScriptRequest(BaseModel):
    """Structured input to a scriptwriter ``generate()`` call.

    Metadata-only — the request is small JSON, never binary. Each
    provider is free to project the request onto its own prompt template.
    """

    model_config = ConfigDict(extra="forbid")

    job_id: uuid.UUID
    brief: str
    script_text: str | None = None
    target_duration_seconds: int
    language: str = "en"
    tone: str | None = None
    platform: str | None = None       # "reels" | "tiktok" | "shorts" | ...
    audience: str | None = None
    safety_constraints: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Phase 21 iter 2 — output mode. "spoken_script" (default) produces
    # a voiceable script; "image_description" produces a short visual
    # prompt suitable for FLUX/SD3.5 (used by the talking-head form's
    # "Generate image description" button to drive character image
    # generation). Providers that don't understand the field treat the
    # request as the default spoken_script mode.
    mode: str = "spoken_script"


class ScriptResult(BaseModel):
    """Structured output of a scriptwriter ``generate()`` call.

    A raw string is intentionally NOT acceptable as a result — every
    downstream stage (voice, editor, qc) reads structured fields. This
    keeps the contract stable as backends swap.
    """

    model_config = ConfigDict(extra="forbid")

    hook: str
    body: str
    cta: str
    full_script: str
    estimated_duration_seconds: float
    language: str
    provider: str
    model: str
    prompt_version: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScriptProvider(ABC):
    """Abstract base for scriptwriter backends.

    Subclasses set the ``provider_name`` ClassVar to a stable id
    (referenced by ``SCRIPTWRITER_BACKEND`` and the registry).
    ``model_name`` is an instance attribute so providers can carry
    their currently-configured model (e.g. ``qwen3.6`` for Ollama).
    """

    provider_name: ClassVar[str] = ""
    supports_streaming: ClassVar[bool] = False
    supports_json_mode: ClassVar[bool] = False

    def __init__(self, *, model_name: str = "") -> None:
        self.model_name = model_name

    @abstractmethod
    def required_config(self) -> list[str]:
        """List of env-var names the provider needs to be operational.

        ``healthcheck()`` checks for these (returning ``not_configured``
        if any are missing). For the template provider this list is
        empty.
        """

    @abstractmethod
    def healthcheck(self) -> ProviderHealth:
        """Return a structured ``ProviderHealth`` describing the current
        configuration state — never raises. The DAG handler uses this to
        decide whether to attempt ``generate()`` or fall back."""

    @abstractmethod
    async def generate(self, req: ScriptRequest) -> ScriptResult:
        """Produce a structured ScriptResult.

        Phase 3G providers other than ``template`` raise
        ``ProviderNotImplementedError`` here. The future Phase that
        activates a real backend will replace this body with a lazy
        import + bounded HTTP call.
        """
