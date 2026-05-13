"""vLLM provider — Phase 3G stub.

vLLM exposes an OpenAI-compatible HTTP API, so a future implementation
will look very similar to ``openai_compatible``. Keeping them separate
gives operators an explicit choice in ``.env``: ``SCRIPTWRITER_BACKEND``
selects between ``vllm`` and a generic ``openai_compatible`` endpoint.

Configuration:

- ``VLLM_BASE_URL`` (default ``http://localhost:8000/v1``).
- ``VLLM_MODEL`` (default ``qwen3.6``).
- ``VLLM_FALLBACK_MODEL`` (default ``qwen3:8b``).
"""
from __future__ import annotations

import os
from typing import ClassVar

from common.enums import ProviderHealthStatus
from common.exceptions import ProviderNotImplementedError
from common.schemas import ProviderHealth

from agents.scriptwriter.core.provider import (
    ScriptProvider,
    ScriptRequest,
    ScriptResult,
)


class VLLMProvider(ScriptProvider):
    provider_name: ClassVar[str] = "vllm"

    def __init__(self) -> None:
        model = os.environ.get("VLLM_MODEL", "qwen3.6")
        super().__init__(model_name=model)
        self._base_url = os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
        self._fallback_model = os.environ.get("VLLM_FALLBACK_MODEL", "qwen3:8b")

    def required_config(self) -> list[str]:
        return ["VLLM_BASE_URL", "VLLM_MODEL"]

    def healthcheck(self) -> ProviderHealth:
        return ProviderHealth(
            backend=self.provider_name,
            status=ProviderHealthStatus.not_implemented,
            errors=[
                "vllm: real network calls are deferred (Phase 3G stub)."
            ],
            extra={
                "base_url": self._base_url,
                "preferred_model": self.model_name,
                "fallback_model": self._fallback_model,
                "openai_compatible": True,
                "calls_external_apis": False,
            },
        )

    async def generate(self, req: ScriptRequest) -> ScriptResult:
        raise ProviderNotImplementedError(
            "vllm: real generation not implemented in Phase 3G."
        )
