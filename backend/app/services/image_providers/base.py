"""Abstract image-provider interface — Phase 12.

Mirrors the shape the spec calls out:

::

    ImageProvider {
      id: string
      displayName: string
      status: available | unavailable | not_configured | error
      capabilities: { textToImage, imageToImage, referenceImage,
                      multiReference, negativePrompt, seed, local, api }
      generateTextToImage(input)
      generateImageToImage(input)
      healthCheck()
    }
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ImageProviderHealthStatus = Literal[
    "available",
    "configured",
    "unavailable",
    "not_configured",
    "error",
]


# ---------------------------------------------------------------------------
# Public dataclasses (no Pydantic — these are internal contract objects;
# the router layer converts them to/from the public schema).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderCapabilities:
    text_to_image: bool = True
    image_to_image: bool = False
    reference_image: bool = False
    multi_reference: bool = False
    negative_prompt: bool = True
    seed: bool = True
    local: bool = False
    api: bool = False


@dataclass(frozen=True)
class ProviderHealth:
    status: ImageProviderHealthStatus
    notes: str = ""


@dataclass(frozen=True)
class ImageGenerationInput:
    prompt: str | None
    negative_prompt: str | None
    model_id: str | None
    seed: int | None
    width: int
    height: int
    steps: int | None
    guidance_scale: float | None
    reference_image_path: str | None
    # Phase IG-1 — identity-consistent generation. ``face_reference_path``
    # anchors facial identity (PuLID / InstantID / IP-Adapter-FaceID);
    # ``body_reference_path`` anchors silhouette/proportions. ``workflow_name``
    # selects a ComfyUI template file under ``COMFYUI_WORKFLOW_DIR`` (e.g.
    # "pulid_flux_consistent"); when unset the provider falls back to the
    # single ``COMFYUI_WORKFLOW_PATH`` template (back-compat).
    face_reference_path: str | None = None
    body_reference_path: str | None = None
    workflow_name: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ImageGenerationResult:
    """Outcome of a successful generate call.

    ``image_bytes`` carries the raw PNG; the router persists it via the
    storage abstraction and registers a ``CharacterImage`` row.
    """

    image_bytes: bytes
    mime_type: str
    width: int
    height: int
    seed: int | None
    model_id: str | None
    provider_metadata: dict


# ---------------------------------------------------------------------------
# Categorised error
# ---------------------------------------------------------------------------


class ProviderUnavailableError(Exception):
    """Raised when a provider cannot fulfil a generate request.

    ``error_code`` mirrors the literal set on
    :class:`app.schemas.character.CharacterImageGenerateError` so the
    router can pass it straight through.
    """

    def __init__(self, error_code: str, detail: str, *, fallback: str | None = None) -> None:
        super().__init__(detail)
        self.error_code = error_code
        self.detail = detail
        self.fallback = fallback


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class ImageProvider:
    """Abstract base for every image-generation backend.

    Subclasses must set ``provider_id``, ``display_name``, and override
    :meth:`health_check` + :meth:`generate_text_to_image`. They may
    additionally override :meth:`generate_image_to_image` if the
    underlying model supports reference-image conditioning.
    """

    provider_id: str = ""
    display_name: str = ""
    capabilities: ProviderCapabilities = ProviderCapabilities()
    default_model: str | None = None

    async def health_check(self) -> ProviderHealth:
        raise NotImplementedError

    async def generate_text_to_image(
        self, request: ImageGenerationInput
    ) -> ImageGenerationResult:
        raise NotImplementedError

    async def generate_image_to_image(
        self, request: ImageGenerationInput
    ) -> ImageGenerationResult:
        if not self.capabilities.image_to_image:
            raise ProviderUnavailableError(
                "provider_not_implemented",
                f"Provider {self.provider_id!r} does not support image-to-image.",
            )
        raise NotImplementedError
