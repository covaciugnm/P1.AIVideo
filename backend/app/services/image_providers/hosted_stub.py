"""Hosted-API image providers (Phase 12 stubs).

Covers FLUX BFL hosted API, Stability AI, Replicate, fal.ai,
together.ai, OpenAI DALL·E 3, Ideogram, Recraft, Vertex AI Imagen 3,
and a (fragile, unofficial) Midjourney proxy adapter.

Each provider validates its env credentials and — until the operator
opts in by setting both the API key AND the global
``IMAGE_GENERATOR_ENABLE_NETWORK_CALLS=true`` flag (mirrors the
existing ``SCRIPTWRITER_ENABLE_NETWORK_CALLS`` gate) — refuses to
make outbound calls. This keeps the no-credentials dev path safe and
mirrors the project's "metadata first, real call later" convention.

The real SDK invocations are out of scope for this phase; the stub
returns a categorised :class:`ProviderUnavailableError` so the router
surfaces a clean operator message rather than fabricating an image.
"""
from __future__ import annotations

import logging
import os

from app.services.image_providers.base import (
    ImageGenerationInput,
    ImageGenerationResult,
    ImageProvider,
    ProviderCapabilities,
    ProviderHealth,
    ProviderUnavailableError,
)

logger = logging.getLogger(__name__)


_NETWORK_ENABLE_ENV = "IMAGE_GENERATOR_ENABLE_NETWORK_CALLS"


def _network_calls_enabled() -> bool:
    return os.environ.get(_NETWORK_ENABLE_ENV, "false").lower() in ("true", "1", "yes")


class HostedApiImageProviderStub(ImageProvider):
    capabilities = ProviderCapabilities(
        text_to_image=True,
        image_to_image=False,
        reference_image=False,
        multi_reference=False,
        negative_prompt=True,
        seed=True,
        local=False,
        api=True,
    )
    api_key_envs: tuple[str, ...] = ()
    docs_url: str = ""
    runtime_label: str = ""
    supports_reference: bool = False

    @classmethod
    def build(
        cls,
        *,
        provider_id: str,
        display_name: str,
        default_model: str | None,
        api_key_envs: tuple[str, ...],
        runtime_label: str = "",
        supports_reference: bool = False,
    ) -> "HostedApiImageProviderStub":
        instance = cls()
        instance.provider_id = provider_id
        instance.display_name = display_name
        instance.default_model = default_model
        instance.api_key_envs = api_key_envs
        instance.runtime_label = runtime_label or display_name
        instance.supports_reference = supports_reference
        if supports_reference:
            instance.capabilities = ProviderCapabilities(
                text_to_image=True,
                image_to_image=True,
                reference_image=True,
                multi_reference=False,
                negative_prompt=True,
                seed=True,
                local=False,
                api=True,
            )
        return instance

    def _missing_credentials(self) -> list[str]:
        return [e for e in self.api_key_envs if not os.environ.get(e, "").strip()]

    async def health_check(self) -> ProviderHealth:
        missing = self._missing_credentials()
        if missing:
            return ProviderHealth(
                status="not_configured",
                notes=f"Missing env vars: {', '.join(missing)}.",
            )
        if not _network_calls_enabled():
            return ProviderHealth(
                status="configured",
                notes=(
                    f"{self.runtime_label} credentials present, but outbound "
                    f"calls are disabled (set {_NETWORK_ENABLE_ENV}=true to "
                    "enable real generation)."
                ),
            )
        return ProviderHealth(
            status="configured",
            notes=(
                f"{self.runtime_label} credentials present and network calls "
                "enabled. Real adapter wiring lands in a follow-up phase."
            ),
        )

    async def generate_text_to_image(
        self, request: ImageGenerationInput
    ) -> ImageGenerationResult:
        missing = self._missing_credentials()
        if missing:
            raise ProviderUnavailableError(
                "provider_not_configured",
                f"{self.runtime_label} requires env vars: {', '.join(missing)}.",
                fallback="mock",
            )
        if not _network_calls_enabled():
            raise ProviderUnavailableError(
                "provider_not_configured",
                (
                    f"{self.runtime_label} outbound calls are disabled. "
                    f"Set {_NETWORK_ENABLE_ENV}=true to permit the backend "
                    "to issue real generation requests."
                ),
                fallback="mock",
            )
        # Phase 12 boundary — the SDK wiring is intentionally not
        # included in this commit. The categorised error keeps the
        # operator informed instead of fabricating an image.
        raise ProviderUnavailableError(
            "provider_not_implemented",
            (
                f"{self.runtime_label} adapter is a stub in this phase. "
                "The HTTP SDK call has not been wired yet — track the "
                "follow-up implementation phase for real generation."
            ),
            fallback="mock",
        )

    async def generate_image_to_image(
        self, request: ImageGenerationInput
    ) -> ImageGenerationResult:
        if not self.supports_reference:
            raise ProviderUnavailableError(
                "provider_not_implemented",
                f"{self.runtime_label} does not support image-to-image.",
                fallback="mock",
            )
        # Same gating as text-to-image — credentials + network gate first.
        return await self.generate_text_to_image(request)


# Hosted-API provider definitions. ``supports_reference`` reflects whether
# the upstream documents an image-conditioning path (kept honest so the
# capability matrix the UI uses is meaningful).
HOSTED_API_DEFINITIONS: tuple[dict, ...] = (
    {
        "provider_id": "flux_bfl_api",
        "display_name": "FLUX BFL hosted API",
        "default_model": "flux-pro-1.1",
        "api_key_envs": ("FLUX_BFL_API_KEY",),
        "runtime_label": "FLUX (BFL)",
        "supports_reference": True,
    },
    {
        "provider_id": "stability_api",
        "display_name": "Stability AI hosted",
        "default_model": "stable-image-ultra",
        "api_key_envs": ("STABILITY_API_KEY",),
        "runtime_label": "Stability AI",
        "supports_reference": True,
    },
    {
        "provider_id": "replicate_api",
        "display_name": "Replicate.com",
        "default_model": "black-forest-labs/flux-schnell",
        "api_key_envs": ("REPLICATE_API_TOKEN",),
        "runtime_label": "Replicate",
        "supports_reference": True,
    },
    {
        "provider_id": "fal_api",
        "display_name": "fal.ai",
        "default_model": "fal-ai/flux/schnell",
        "api_key_envs": ("FAL_KEY",),
        "runtime_label": "fal.ai",
        "supports_reference": True,
    },
    {
        "provider_id": "together_api",
        "display_name": "together.ai",
        "default_model": "black-forest-labs/FLUX.1-schnell",
        "api_key_envs": ("TOGETHER_API_KEY",),
        "runtime_label": "Together.ai",
        "supports_reference": False,
    },
    {
        "provider_id": "openai_dalle3",
        "display_name": "OpenAI DALL·E 3",
        "default_model": "dall-e-3",
        "api_key_envs": ("OPENAI_API_KEY",),
        "runtime_label": "OpenAI DALL·E",
        "supports_reference": False,
    },
    {
        "provider_id": "ideogram_api",
        "display_name": "Ideogram",
        "default_model": "ideogram-v2",
        "api_key_envs": ("IDEOGRAM_API_KEY",),
        "runtime_label": "Ideogram",
        "supports_reference": False,
    },
    {
        "provider_id": "recraft_api",
        "display_name": "Recraft",
        "default_model": "recraftv3",
        "api_key_envs": ("RECRAFT_API_KEY",),
        "runtime_label": "Recraft",
        "supports_reference": True,
    },
    {
        "provider_id": "vertex_imagen3",
        "display_name": "Google Vertex AI — Imagen 3",
        "default_model": "imagen-3.0-generate-002",
        "api_key_envs": ("VERTEX_AI_PROJECT_ID", "GOOGLE_APPLICATION_CREDENTIALS"),
        "runtime_label": "Vertex Imagen 3",
        "supports_reference": False,
    },
    {
        "provider_id": "midjourney_unofficial",
        "display_name": "Midjourney (unofficial proxy)",
        "default_model": "midjourney-v6",
        "api_key_envs": ("MIDJOURNEY_PROXY_URL", "MIDJOURNEY_PROXY_TOKEN"),
        "runtime_label": "Midjourney (unofficial)",
        "supports_reference": True,
    },
)
