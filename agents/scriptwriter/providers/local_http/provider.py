"""Local HTTP provider — Phase 3G stub.

Generic HTTP endpoint for self-hosted services that aren't OpenAI-
compatible (e.g. a custom internal generation service). A future phase
will use the stdlib ``urllib`` or ``httpx`` to call this endpoint —
deliberately keeping the dep surface minimal.

Configuration:

- ``LOCAL_LLM_URL``
- ``LOCAL_LLM_MODEL`` (default ``qwen3.6``)
- ``LOCAL_LLM_TIMEOUT_SECONDS`` (default 60)
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


class LocalHTTPProvider(ScriptProvider):
    provider_name: ClassVar[str] = "local_http"

    def __init__(self) -> None:
        super().__init__(model_name=os.environ.get("LOCAL_LLM_MODEL", "qwen3.6"))
        self._url = os.environ.get("LOCAL_LLM_URL", "")
        try:
            self._timeout = int(os.environ.get("LOCAL_LLM_TIMEOUT_SECONDS", "60") or "60")
        except ValueError:
            self._timeout = 60

    def required_config(self) -> list[str]:
        return ["LOCAL_LLM_URL", "LOCAL_LLM_MODEL"]

    def healthcheck(self) -> ProviderHealth:
        if not self._url:
            return ProviderHealth(
                backend=self.provider_name,
                status=ProviderHealthStatus.not_configured,
                errors=["local_http: LOCAL_LLM_URL is unset."],
                extra={"calls_external_apis": False},
            )
        return ProviderHealth(
            backend=self.provider_name,
            status=ProviderHealthStatus.not_implemented,
            errors=[
                "local_http: URL configured but real network calls are "
                "deferred (Phase 3G stub)."
            ],
            extra={
                "url": self._url,
                "model": self.model_name,
                "timeout_seconds": self._timeout,
                "calls_external_apis": False,
            },
        )

    async def generate(self, req: ScriptRequest) -> ScriptResult:
        raise ProviderNotImplementedError(
            "local_http: real generation not implemented in Phase 3G."
        )
