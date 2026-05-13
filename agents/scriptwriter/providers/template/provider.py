"""Template provider — Phase 3G default scriptwriter.

Deterministic, dependency-free script generation. Useful for:

- offline DAG runs without a live LLM;
- unit + integration tests that need a stable, reproducible script;
- a safe default when ``SCRIPTWRITER_BACKEND`` is unset.

If the operator supplies ``script_text`` on the request, the provider
splits it into ``hook``/``body``/``cta`` segments using paragraph
boundaries (with sentence fallback). Otherwise it derives a placeholder
script from the ``brief``. Either way the result is fully structured.
"""
from __future__ import annotations

import os
from typing import ClassVar

from common.enums import ProviderHealthStatus
from common.schemas import ProviderHealth

from agents.scriptwriter.core.provider import (
    ScriptProvider,
    ScriptRequest,
    ScriptResult,
)


class TemplateProvider(ScriptProvider):
    provider_name: ClassVar[str] = "template"

    def __init__(self) -> None:
        super().__init__(model_name="template-v1")
        self._prompt_version = os.environ.get("SCRIPTWRITER_PROMPT_VERSION", "v1")

    # --------------------------------------------------------------- contract

    def required_config(self) -> list[str]:
        return []  # template needs nothing

    def healthcheck(self) -> ProviderHealth:
        return ProviderHealth(
            backend=self.provider_name,
            status=ProviderHealthStatus.ok,
            extra={
                "model": self.model_name,
                "prompt_version": self._prompt_version,
                "deterministic": True,
                "calls_external_apis": False,
            },
        )

    async def generate(self, req: ScriptRequest) -> ScriptResult:
        hook, body, cta = self._split_or_derive(req)
        full_script = "\n\n".join(part.strip() for part in (hook, body, cta) if part.strip())

        return ScriptResult(
            hook=hook,
            body=body,
            cta=cta,
            full_script=full_script,
            estimated_duration_seconds=float(req.target_duration_seconds),
            language=req.language,
            provider=self.provider_name,
            model=self.model_name,
            prompt_version=self._prompt_version,
            metadata={
                "deterministic": True,
                "source": "operator_text" if req.script_text else "brief_derived",
                "platform": req.platform,
                "tone": req.tone,
                "audience": req.audience,
            },
        )

    # ---------------------------------------------------------------- helpers

    def _split_or_derive(self, req: ScriptRequest) -> tuple[str, str, str]:
        text = (req.script_text or "").strip()
        if text:
            return self._split_text(text)
        # No script provided — derive a placeholder from the brief. The
        # text is intentionally non-LLM and only useful as a structural
        # placeholder for downstream stages.
        brief = req.brief.strip()
        hook = f"Quick: {brief}"
        body = (
            "Here is what to know. "
            f"This reel is about: {brief}. "
            "Key points are covered concisely; replace this body with a real script "
            "once a real LLM backend is enabled."
        )
        cta = "Save this for later or share it with a friend."
        return hook, body, cta

    @staticmethod
    def _split_text(text: str) -> tuple[str, str, str]:
        # Prefer paragraph splits when the operator supplies multi-paragraph text.
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if len(paragraphs) >= 3:
            return paragraphs[0], "\n\n".join(paragraphs[1:-1]), paragraphs[-1]
        if len(paragraphs) == 2:
            return paragraphs[0], paragraphs[1], "Thanks for watching."
        # Single-paragraph fallback: use sentences.
        sentences = [s.strip() for s in text.replace("!", ".").replace("?", ".").split(".") if s.strip()]
        if not sentences:
            return text, text, "Thanks for watching."
        if len(sentences) == 1:
            return sentences[0], sentences[0], "Thanks for watching."
        if len(sentences) == 2:
            return sentences[0], sentences[1], "Thanks for watching."
        return sentences[0], ". ".join(sentences[1:-1]) + ".", sentences[-1]
