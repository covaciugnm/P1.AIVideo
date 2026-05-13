"""OpenAI provider — Phase 3G stub.

Configuration (read at construction; not validated against the OpenAI
service in this phase):

- ``OPENAI_API_KEY``
- ``OPENAI_MODEL``
- ``OPENAI_TIMEOUT_SECONDS`` (default 60)

Phase 3G: the ``openai`` Python package is NOT a project dependency.
A future phase that activates this backend will lazy-import it inside
``generate()`` and key access will be gated on
``SCRIPTWRITER_ENABLE_NETWORK_CALLS=true``.
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


class OpenAIProvider(ScriptProvider):
    provider_name: ClassVar[str] = "openai"

    def __init__(self) -> None:
        super().__init__(model_name=os.environ.get("OPENAI_MODEL", ""))
        self._has_api_key = bool(os.environ.get("OPENAI_API_KEY", ""))
        try:
            self._timeout = int(os.environ.get("OPENAI_TIMEOUT_SECONDS", "60") or "60")
        except ValueError:
            self._timeout = 60

    def required_config(self) -> list[str]:
        return ["OPENAI_API_KEY", "OPENAI_MODEL"]

    def healthcheck(self) -> ProviderHealth:
        if not self._has_api_key or not self.model_name:
            return ProviderHealth(
                backend=self.provider_name,
                status=ProviderHealthStatus.not_configured,
                errors=[
                    "openai: OPENAI_API_KEY or OPENAI_MODEL is unset."
                ],
                extra={"calls_external_apis": False},
            )
        return ProviderHealth(
            backend=self.provider_name,
            status=ProviderHealthStatus.not_implemented,
            errors=[
                "openai: API key + model present but real network calls "
                "are deferred (Phase 3G stub)."
            ],
            extra={
                "model": self.model_name,
                "timeout_seconds": self._timeout,
                "calls_external_apis": False,
            },
        )

    async def generate(self, req: ScriptRequest) -> ScriptResult:
        raise ProviderNotImplementedError(
            "openai: real generation not implemented in Phase 3G."
        )
