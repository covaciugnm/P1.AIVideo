"""Anthropic provider — Phase 3G stub.

Configuration:

- ``ANTHROPIC_API_KEY``
- ``ANTHROPIC_MODEL``
- ``ANTHROPIC_TIMEOUT_SECONDS`` (default 60)

Phase 3G: the ``anthropic`` Python package is NOT a project dependency.
A future phase will lazy-import it inside ``generate()``.
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


class AnthropicProvider(ScriptProvider):
    provider_name: ClassVar[str] = "anthropic"

    def __init__(self) -> None:
        super().__init__(model_name=os.environ.get("ANTHROPIC_MODEL", ""))
        self._has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY", ""))
        try:
            self._timeout = int(os.environ.get("ANTHROPIC_TIMEOUT_SECONDS", "60") or "60")
        except ValueError:
            self._timeout = 60

    def required_config(self) -> list[str]:
        return ["ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"]

    def healthcheck(self) -> ProviderHealth:
        if not self._has_api_key or not self.model_name:
            return ProviderHealth(
                backend=self.provider_name,
                status=ProviderHealthStatus.not_configured,
                errors=[
                    "anthropic: ANTHROPIC_API_KEY or ANTHROPIC_MODEL is unset."
                ],
                extra={"calls_external_apis": False},
            )
        return ProviderHealth(
            backend=self.provider_name,
            status=ProviderHealthStatus.not_implemented,
            errors=[
                "anthropic: API key + model present but real network calls "
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
            "anthropic: real generation not implemented in Phase 3G."
        )
