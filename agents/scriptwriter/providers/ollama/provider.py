"""Ollama provider — Phase 3G stub.

Configuration:

- ``OLLAMA_BASE_URL`` (default ``http://localhost:11434``).
- ``OLLAMA_MODEL`` (default ``qwen3.6`` — the project's preferred local model).
- ``OLLAMA_FALLBACK_MODEL`` (default ``qwen3:8b`` — smaller fallback).

Activation in a later phase: a lazy HTTP call inside ``generate()``
behind ``SCRIPTWRITER_ENABLE_NETWORK_CALLS=true``. Phase 3G ships only
the contract — no client import, no HTTP, no model download.
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


class OllamaProvider(ScriptProvider):
    provider_name: ClassVar[str] = "ollama"

    def __init__(self) -> None:
        model = os.environ.get("OLLAMA_MODEL", "qwen3.6")
        super().__init__(model_name=model)
        self._base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        self._fallback_model = os.environ.get("OLLAMA_FALLBACK_MODEL", "qwen3:8b")

    def required_config(self) -> list[str]:
        return ["OLLAMA_BASE_URL", "OLLAMA_MODEL"]

    def healthcheck(self) -> ProviderHealth:
        return ProviderHealth(
            backend=self.provider_name,
            status=ProviderHealthStatus.not_implemented,
            errors=[
                "ollama: real network calls are deferred (Phase 3G stub). "
                "Generate() will refuse until a future phase enables it."
            ],
            extra={
                "base_url": self._base_url,
                "preferred_model": self.model_name,
                "fallback_model": self._fallback_model,
                "calls_external_apis": False,
            },
        )

    async def generate(self, req: ScriptRequest) -> ScriptResult:
        raise ProviderNotImplementedError(
            "ollama: real generation not implemented in Phase 3G; "
            "set SCRIPTWRITER_BACKEND=template for the deterministic provider."
        )
