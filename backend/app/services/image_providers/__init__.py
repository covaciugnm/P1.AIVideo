"""Image generation providers — Phase 12.

The :class:`ImageProvider` abstract base + concrete adapters live
here. Operators select a backend by ``provider_id``; the registry
already lists 16 of them (1 mock + 5 local wrappers + 10 hosted APIs).

Only the ``mock`` provider runs without operator setup; everything
else raises :class:`ProviderUnavailableError` with a categorised
``error_code`` until the wrapper / API key is wired. The router layer
translates the exception into the structured
:class:`app.schemas.character.CharacterImageGenerateError` payload.
"""
from __future__ import annotations

from app.services.image_providers.base import (
    ImageGenerationInput,
    ImageGenerationResult,
    ImageProvider,
    ProviderCapabilities,
    ProviderHealth,
    ProviderUnavailableError,
)
from app.services.image_providers.dispatch import (
    PROVIDER_ID_TO_BACKEND,
    available_provider_ids,
    get_image_provider,
    is_provider_known,
)
from app.services.image_providers.mock_provider import MockImageProvider
from app.services.image_providers.hosted_stub import HostedApiImageProviderStub
from app.services.image_providers.local_wrapper_stub import LocalWrapperImageProviderStub

__all__ = [
    "HostedApiImageProviderStub",
    "ImageGenerationInput",
    "ImageGenerationResult",
    "ImageProvider",
    "LocalWrapperImageProviderStub",
    "MockImageProvider",
    "PROVIDER_ID_TO_BACKEND",
    "ProviderCapabilities",
    "ProviderHealth",
    "ProviderUnavailableError",
    "available_provider_ids",
    "get_image_provider",
    "is_provider_known",
]
