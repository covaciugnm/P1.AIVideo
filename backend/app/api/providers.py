"""Provider metadata endpoints (Phase 4F + Phase 6D + Phase 12).

All six provider categories are served:
- LLM
- TTS
- Video generator
- Audio processor (Phase 6D)
- Image processor (Phase 6D)
- Image generator (Phase 12 — Characters tab)

The endpoint layer is a thin pass-through to
:mod:`app.services.provider_registry` with operator overrides merged
in from the ``feature_providers`` DB table (Phase 12). Every record
is metadata-only — no secrets, no API keys, no endpoint URLs
containing tokens.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.core.deps import get_db_session
from app.schemas.providers import ProviderInfo, ProvidersResponse
from app.services import feature_provider_service, provider_registry

router = APIRouter(prefix="/api/v1/providers", tags=["providers"])


async def _load_overrides(session: AsyncSession) -> dict[tuple[str, str], dict]:
    """Best-effort fetch of operator overrides.

    Failures (e.g. table missing on a pre-Phase-12 DB) are swallowed
    so the catalog stays available even when the DB layer is being
    migrated.
    """
    try:
        return await feature_provider_service.load_overrides(session)
    except Exception:
        return {}


def _merge(
    catalog: list[ProviderInfo],
    overrides: dict[tuple[str, str], dict],
) -> list[ProviderInfo]:
    return provider_registry.apply_feature_provider_overrides(catalog, overrides)


@router.get("", response_model=ProvidersResponse)
async def list_providers(
    session: AsyncSession = Depends(get_db_session),
) -> ProvidersResponse:
    overrides = await _load_overrides(session)
    catalogs = provider_registry.list_providers()
    return ProvidersResponse(
        llm=_merge(catalogs["llm"], overrides),
        tts=_merge(catalogs["tts"], overrides),
        video_generator=_merge(catalogs["video_generator"], overrides),
        audio_processor=_merge(catalogs["audio_processor"], overrides),
        image_processor=_merge(catalogs["image_processor"], overrides),
        image_generator=_merge(catalogs["image_generator"], overrides),
    )


@router.get("/llm", response_model=list[ProviderInfo])
async def list_llm_providers(
    session: AsyncSession = Depends(get_db_session),
) -> list[ProviderInfo]:
    overrides = await _load_overrides(session)
    return _merge(provider_registry.list_providers_by_category("llm"), overrides)


@router.get("/tts", response_model=list[ProviderInfo])
async def list_tts_providers(
    session: AsyncSession = Depends(get_db_session),
) -> list[ProviderInfo]:
    overrides = await _load_overrides(session)
    return _merge(provider_registry.list_providers_by_category("tts"), overrides)


@router.get("/video-generators", response_model=list[ProviderInfo])
async def list_video_providers(
    session: AsyncSession = Depends(get_db_session),
) -> list[ProviderInfo]:
    overrides = await _load_overrides(session)
    return _merge(
        provider_registry.list_providers_by_category("video_generator"), overrides
    )


@router.get("/audio-processors", response_model=list[ProviderInfo])
async def list_audio_processor_providers(
    session: AsyncSession = Depends(get_db_session),
) -> list[ProviderInfo]:
    overrides = await _load_overrides(session)
    return _merge(
        provider_registry.list_providers_by_category("audio_processor"), overrides
    )


@router.get("/image-processors", response_model=list[ProviderInfo])
async def list_image_processor_providers(
    session: AsyncSession = Depends(get_db_session),
) -> list[ProviderInfo]:
    overrides = await _load_overrides(session)
    return _merge(
        provider_registry.list_providers_by_category("image_processor"), overrides
    )


@router.get("/image-generators", response_model=list[ProviderInfo])
async def list_image_generator_providers(
    session: AsyncSession = Depends(get_db_session),
) -> list[ProviderInfo]:
    overrides = await _load_overrides(session)
    return _merge(
        provider_registry.list_providers_by_category("image_generator"), overrides
    )


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
    "image-generators": "image_generator",
    "image_generator": "image_generator",
}


@router.get("/{category}/{provider_id}", response_model=ProviderInfo)
async def get_provider_detail(
    category: str,
    provider_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> ProviderInfo:
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
    overrides = await _load_overrides(session)
    merged = _merge([info], overrides)
    return merged[0]


@router.post("/{category}/{provider_id}/health-check", response_model=ProviderInfo)
async def health_check_provider(
    category: str,
    provider_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> ProviderInfo:
    """Run a best-effort health probe and persist the outcome.

    Mock provider always returns ``available``. Real providers
    (image generators with an HTTP endpoint or API key) get a quick
    reachability check delegated to
    :func:`feature_provider_service.run_health_check`. The endpoint
    is metadata-only — it never generates content or sends prompts.
    """
    canonical = _CATEGORY_SLUGS.get(category)
    if canonical is None:
        raise HTTPException(status_code=404, detail=f"unknown category {category!r}")
    info = provider_registry.get_provider(canonical, provider_id)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown provider {provider_id!r} in category {canonical}",
        )
    new_status, notes = await feature_provider_service.run_health_check(
        session, canonical, provider_id, info
    )
    return info.model_copy(update={"status": new_status, "notes": notes})
