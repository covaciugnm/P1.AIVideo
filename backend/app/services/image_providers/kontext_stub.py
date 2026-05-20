"""FLUX.1 Kontext provider — Phase IG-5 (future image-EDIT provider).

Kontext is reference-driven *editing* ("same person, now in a business
suit"), not first-image generation. Full integration is out of scope for
now, so this provider is a clear, honest stub: every call raises
``provider_not_configured`` (unless ``FLUX_KONTEXT_ENABLED=true`` AND a
``FLUX_KONTEXT_BASE_URL`` is wired, in which case it still returns a
not-implemented error rather than pretending to succeed). It NEVER fakes
a successful generation.
"""
from __future__ import annotations

import os

from app.services.image_providers.base import (
    ImageGenerationInput,
    ImageGenerationResult,
    ImageProvider,
    ProviderCapabilities,
    ProviderHealth,
    ProviderUnavailableError,
)


class FluxKontextProvider(ImageProvider):
    provider_id = "flux_kontext"
    display_name = "FLUX.1 Kontext (reference editing — future)"
    capabilities = ProviderCapabilities(
        text_to_image=False, image_to_image=True, reference_image=True,
        negative_prompt=True, seed=True, local=False, api=True,
    )
    default_model = "flux.1-kontext"

    @staticmethod
    def _enabled() -> bool:
        return os.environ.get("FLUX_KONTEXT_ENABLED", "false").lower() in (
            "true", "1", "yes",
        )

    async def health_check(self) -> ProviderHealth:
        if not self._enabled():
            return ProviderHealth(
                "not_configured",
                "FLUX.1 Kontext is a future edit provider — set "
                "FLUX_KONTEXT_ENABLED=true + FLUX_KONTEXT_BASE_URL to wire it.",
            )
        return ProviderHealth(
            "not_configured",
            "FLUX.1 Kontext integration is not implemented yet (stub).",
        )

    async def generate_text_to_image(
        self, request: ImageGenerationInput
    ) -> ImageGenerationResult:
        raise ProviderUnavailableError(
            "provider_not_implemented",
            "FLUX.1 Kontext is an image-EDIT provider; it does not do "
            "text-to-image. Use the initial workflow instead.",
        )

    async def generate_image_to_image(
        self, request: ImageGenerationInput
    ) -> ImageGenerationResult:
        raise ProviderUnavailableError(
            "provider_not_configured",
            "FLUX.1 Kontext is prepared but not implemented (stub). "
            "Enable + wire FLUX_KONTEXT_BASE_URL and implement the edit call.",
            fallback="comfyui_local",
        )
