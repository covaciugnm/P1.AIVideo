"""Provider lookup + dispatch — Phase 12.

A single entrypoint maps ``provider_id`` → concrete
:class:`ImageProvider` instance. Unknown IDs raise
:class:`ProviderUnavailableError` with ``error_code='provider_unavailable'``
so the router doesn't have to know about the catalog shape.
"""
from __future__ import annotations

from typing import Mapping

from app.services.image_providers.base import (
    ImageProvider,
    ProviderUnavailableError,
)
from app.services.image_providers.hosted_stub import (
    HOSTED_API_DEFINITIONS,
    HostedApiImageProviderStub,
)
from app.services.image_providers.local_wrapper_stub import (
    LOCAL_WRAPPER_DEFINITIONS,
    LocalWrapperImageProviderStub,
)
from app.services.image_providers.kontext_stub import FluxKontextProvider
from app.services.image_providers.mock_provider import MockImageProvider
from app.services.image_providers.remote_engine_stub import RemoteEngineImageProvider


def _build_registry() -> dict[str, ImageProvider]:
    out: dict[str, ImageProvider] = {"mock": MockImageProvider()}
    for d in LOCAL_WRAPPER_DEFINITIONS:
        out[d["provider_id"]] = LocalWrapperImageProviderStub.build(**d)
    for d in HOSTED_API_DEFINITIONS:
        out[d["provider_id"]] = HostedApiImageProviderStub.build(**d)
    # Phase IG-5 — future reference-edit provider (clear "not configured").
    out["flux_kontext"] = FluxKontextProvider()
    # Remote LAN engine (e.g. GB10 / ThinkStation) — Bearer-authenticated HTTP.
    out[RemoteEngineImageProvider.provider_id] = RemoteEngineImageProvider()
    return out


_REGISTRY: dict[str, ImageProvider] = _build_registry()


# Convenience map for the catalog (provider_id -> backend_type string).
PROVIDER_ID_TO_BACKEND: Mapping[str, str] = {
    pid: provider.__class__.__name__ for pid, provider in _REGISTRY.items()
}


def get_image_provider(provider_id: str) -> ImageProvider:
    if provider_id not in _REGISTRY:
        raise ProviderUnavailableError(
            "provider_unavailable",
            f"Unknown image provider {provider_id!r}. "
            f"Available: {sorted(_REGISTRY.keys())}.",
            fallback="mock",
        )
    return _REGISTRY[provider_id]


def is_provider_known(provider_id: str) -> bool:
    return provider_id in _REGISTRY


def available_provider_ids() -> tuple[str, ...]:
    return tuple(_REGISTRY.keys())
