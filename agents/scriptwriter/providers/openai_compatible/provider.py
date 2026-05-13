"""OpenAI-compatible HTTP provider — Phase 3G stub.

This provider is the future target for any endpoint that speaks the
OpenAI ``/v1/chat/completions`` shape but isn't OpenAI itself:

- Ollama's OpenAI-compatible endpoint
- vLLM (when not using the dedicated ``vllm`` backend)
- LM Studio
- LocalAI
- OpenRouter-style proxies
- internal company endpoints

Configuration:

- ``OPENAI_COMPATIBLE_BASE_URL``
- ``OPENAI_COMPATIBLE_API_KEY`` (optional for local endpoints)
- ``OPENAI_COMPATIBLE_MODEL``
- ``OPENAI_COMPATIBLE_TIMEOUT_SECONDS`` (default 60)

Phase 3G: the ``openai`` Python client is NOT a dependency. A future
phase will lazy-import it inside ``generate()`` (or use a stdlib HTTP
client to avoid the dep entirely).
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


class OpenAICompatibleProvider(ScriptProvider):
    provider_name: ClassVar[str] = "openai_compatible"

    def __init__(self) -> None:
        model = os.environ.get("OPENAI_COMPATIBLE_MODEL", "")
        super().__init__(model_name=model)
        self._base_url = os.environ.get("OPENAI_COMPATIBLE_BASE_URL", "")
        self._has_api_key = bool(os.environ.get("OPENAI_COMPATIBLE_API_KEY", ""))
        try:
            self._timeout = int(
                os.environ.get("OPENAI_COMPATIBLE_TIMEOUT_SECONDS", "60") or "60"
            )
        except ValueError:
            self._timeout = 60

    def required_config(self) -> list[str]:
        return ["OPENAI_COMPATIBLE_BASE_URL", "OPENAI_COMPATIBLE_MODEL"]

    def healthcheck(self) -> ProviderHealth:
        if not self._base_url or not self.model_name:
            return ProviderHealth(
                backend=self.provider_name,
                status=ProviderHealthStatus.not_configured,
                errors=[
                    "openai_compatible: OPENAI_COMPATIBLE_BASE_URL or "
                    "OPENAI_COMPATIBLE_MODEL is unset."
                ],
                extra={"calls_external_apis": False},
            )
        return ProviderHealth(
            backend=self.provider_name,
            status=ProviderHealthStatus.not_implemented,
            errors=[
                "openai_compatible: configuration present but real network "
                "calls are deferred (Phase 3G stub)."
            ],
            extra={
                "base_url": self._base_url,
                "model": self.model_name,
                "timeout_seconds": self._timeout,
                "api_key_set": self._has_api_key,
                "calls_external_apis": False,
            },
        )

    async def generate(self, req: ScriptRequest) -> ScriptResult:
        raise ProviderNotImplementedError(
            "openai_compatible: real generation not implemented in Phase 3G."
        )
