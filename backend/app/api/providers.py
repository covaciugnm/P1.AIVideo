"""Provider metadata endpoints (Phase 4F + Phase 6D).

All five Phase 6D categories are served:
- LLM
- TTS
- Video generator
- Audio processor (Phase 6D)
- Image processor (Phase 6D)

The endpoint layer is a thin pass-through to
:mod:`app.services.provider_registry`. Every record is metadata-only —
no secrets, no API keys, no endpoint URLs containing tokens.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas.providers import ProviderInfo, ProvidersResponse
from app.services import provider_registry

router = APIRouter(prefix="/api/v1/providers", tags=["providers"])


@router.get("", response_model=ProvidersResponse)
async def list_providers() -> ProvidersResponse:
    catalogs = provider_registry.list_providers()
    return ProvidersResponse(
        llm=catalogs["llm"],
        tts=catalogs["tts"],
        video_generator=catalogs["video_generator"],
        audio_processor=catalogs["audio_processor"],
        image_processor=catalogs["image_processor"],
    )


@router.get("/llm", response_model=list[ProviderInfo])
async def list_llm_providers() -> list[ProviderInfo]:
    return provider_registry.list_providers_by_category("llm")


@router.get("/tts", response_model=list[ProviderInfo])
async def list_tts_providers() -> list[ProviderInfo]:
    return provider_registry.list_providers_by_category("tts")


@router.get("/video-generators", response_model=list[ProviderInfo])
async def list_video_providers() -> list[ProviderInfo]:
    return provider_registry.list_providers_by_category("video_generator")


@router.get("/audio-processors", response_model=list[ProviderInfo])
async def list_audio_processor_providers() -> list[ProviderInfo]:
    return provider_registry.list_providers_by_category("audio_processor")


@router.get("/image-processors", response_model=list[ProviderInfo])
async def list_image_processor_providers() -> list[ProviderInfo]:
    return provider_registry.list_providers_by_category("image_processor")


# Spec-optional per-provider lookup. Accepts both URL-style slugs
# (``video-generators``) and the canonical snake_case category names
# (``video_generator``).
_CATEGORY_SLUGS = {
    "llm": "llm",
    "tts": "tts",
    "video-generators": "video_generator",
    "video_generator": "video_generator",
    "audio-processors": "audio_processor",
    "audio_processor": "audio_processor",
    "image-processors": "image_processor",
    "image_processor": "image_processor",
}


@router.get("/{category}/{provider_id}", response_model=ProviderInfo)
async def get_provider_detail(category: str, provider_id: str) -> ProviderInfo:
    canonical = _CATEGORY_SLUGS.get(category)
    if canonical is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"unknown category {category!r}; expected one of "
                f"{sorted(set(_CATEGORY_SLUGS.values()))}"
            ),
        )
    info = provider_registry.get_provider(canonical, provider_id)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown provider {provider_id!r} in category {canonical}",
        )
    return info
