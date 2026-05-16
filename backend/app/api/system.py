"""Phase 4B system + config endpoints.

Read-only metadata endpoints the frontend needs so it can render labels,
dropdowns, and a header status indicator without hard-coding the enum
values. Every response is stdlib-friendly JSON; nothing loads models.

Endpoints:

- ``GET /api/v1/stages`` — canonical DAG stages in declared order.
- ``GET /api/v1/artifact-types`` — values of :class:`ArtifactType`.
- ``GET /api/v1/config/ui-options`` — voice/face modes, tts backends,
  duration bounds, upload size caps, accepted mime types.
- ``GET /api/v1/system/status`` — phase + scope + a DB connectivity
  probe. No external requests; no model loading.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from common.enums import (
    CANONICAL_DAG_STAGES,
    ArtifactType,
    JobStatus,
    ProviderHealthStatus,
    StageStatus,
)

from app.core.config import settings
from app.core.deps import get_db_session
from app.core.languages import (
    LANGUAGES,
    catalog_payload,
    is_supported_language,
)
from app.models.operator_settings import SINGLETON_ID, OperatorSettings
from sqlalchemy import select


router = APIRouter(prefix="/api/v1", tags=["system"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class StageInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    order: int
    label: str


class ArtifactTypeInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    label: str


class VoiceModeInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    label: str
    requires_script_text: bool
    requires_audio_artifact: bool


class FaceModeInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    label: str
    requires_image_artifact: bool


class DurationBounds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_seconds: int
    max_seconds: int
    default_seconds: int


class UploadLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audio_max_bytes: int
    image_max_bytes: int
    script_text_max_chars: int
    accepted_audio_mime_types: list[str]
    accepted_image_mime_types: list[str]
    accepted_audio_extensions: list[str]
    accepted_image_extensions: list[str]


class UIOptionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice_modes: list[VoiceModeInfo]
    face_modes: list[FaceModeInfo]
    tts_backends: list[str]
    duration_bounds: DurationBounds
    upload_limits: UploadLimits
    job_statuses: list[str]
    stage_statuses: list[str]
    provider_health_statuses: list[str]
    artifact_types: list[ArtifactTypeInfo]


class SystemStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app_name: str
    app_version: str
    phase: str
    scope: str
    server_time: datetime
    database_reachable: bool
    database_error: str | None = None


# ---------------------------------------------------------------------------
# Static label helpers — no i18n yet; titles are derived from the value.
# ---------------------------------------------------------------------------


def _humanize(value: str) -> str:
    return value.replace("_", " ").title()


# ---------------------------------------------------------------------------
# GET /api/v1/stages
# ---------------------------------------------------------------------------


@router.get("/stages", response_model=list[StageInfo])
async def list_stages() -> list[StageInfo]:
    return [
        StageInfo(name=name, order=idx, label=_humanize(name))
        for idx, name in enumerate(CANONICAL_DAG_STAGES)
    ]


# ---------------------------------------------------------------------------
# GET /api/v1/artifact-types
# ---------------------------------------------------------------------------


@router.get("/artifact-types", response_model=list[ArtifactTypeInfo])
async def list_artifact_types() -> list[ArtifactTypeInfo]:
    return [
        ArtifactTypeInfo(value=at.value, label=_humanize(at.value))
        for at in ArtifactType
    ]


# ---------------------------------------------------------------------------
# GET /api/v1/config/ui-options
# ---------------------------------------------------------------------------


@router.get("/config/ui-options", response_model=UIOptionsResponse)
async def get_ui_options() -> UIOptionsResponse:
    voice_modes = [
        VoiceModeInfo(
            value="tts",
            label="Synthesize with TTS",
            requires_script_text=True,
            requires_audio_artifact=False,
        ),
        VoiceModeInfo(
            value="provided_audio",
            label="Use provided audio",
            requires_script_text=False,
            requires_audio_artifact=True,
        ),
    ]
    face_modes = [
        FaceModeInfo(
            value="provided_image",
            label="Use provided image",
            requires_image_artifact=True,
        ),
    ]
    upload_limits = UploadLimits(
        audio_max_bytes=settings.audio_max_file_size_bytes,
        image_max_bytes=settings.image_max_file_size_bytes,
        script_text_max_chars=settings.script_text_max_chars,
        accepted_audio_mime_types=[
            "audio/wav",
            "audio/x-wav",
            "audio/wave",
            "audio/mpeg",
            "audio/mp4",
            "audio/aac",
            "audio/flac",
            "audio/ogg",
        ],
        accepted_image_mime_types=["image/png", "image/jpeg", "image/webp"],
        accepted_audio_extensions=[".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"],
        accepted_image_extensions=[".png", ".jpg", ".jpeg", ".webp"],
    )
    duration_bounds = DurationBounds(
        min_seconds=settings.min_reel_duration_seconds,
        max_seconds=settings.max_reel_duration_seconds,
        default_seconds=settings.target_duration_seconds,
    )
    return UIOptionsResponse(
        voice_modes=voice_modes,
        face_modes=face_modes,
        tts_backends=["piper"],
        duration_bounds=duration_bounds,
        upload_limits=upload_limits,
        job_statuses=[s.value for s in JobStatus],
        stage_statuses=[s.value for s in StageStatus],
        provider_health_statuses=[s.value for s in ProviderHealthStatus],
        artifact_types=[
            ArtifactTypeInfo(value=at.value, label=_humanize(at.value))
            for at in ArtifactType
        ],
    )


# ---------------------------------------------------------------------------
# GET /api/v1/config/languages — Phase 11A
# ---------------------------------------------------------------------------


class LanguageRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    label_native: str
    label_english: str
    enabled: bool
    rtl: bool


class SubtitleDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    default_language: str
    supported_formats: list[str]
    burn_in_supported: bool


class LanguagesConfigResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_ui_language: str
    default_video_language: str
    available_languages: list[LanguageRow]
    subtitle_defaults: SubtitleDefaults


@router.get("/config/languages", response_model=LanguagesConfigResponse)
async def get_languages_config() -> LanguagesConfigResponse:
    payload = catalog_payload()
    return LanguagesConfigResponse(
        default_ui_language=payload["default_ui_language"],
        default_video_language=payload["default_video_language"],
        available_languages=[LanguageRow(**row) for row in payload["available_languages"]],
        subtitle_defaults=SubtitleDefaults(**payload["subtitle_defaults"]),
    )


# ---------------------------------------------------------------------------
# GET/PATCH /api/v1/settings/ui — Phase 11A (operator-wide singleton)
# ---------------------------------------------------------------------------


class UiSettingsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ui_language: str
    default_video_language: str
    updated_at: datetime


class UiSettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ui_language: str | None = None
    default_video_language: str | None = None


async def _get_or_create_settings(session: AsyncSession) -> OperatorSettings:
    row = await session.execute(
        select(OperatorSettings).where(OperatorSettings.id == SINGLETON_ID)
    )
    existing = row.scalar_one_or_none()
    if existing is not None:
        return existing
    fresh = OperatorSettings(id=SINGLETON_ID)
    session.add(fresh)
    await session.flush()
    return fresh


@router.get("/settings/ui", response_model=UiSettingsResponse)
async def get_ui_settings(
    session: AsyncSession = Depends(get_db_session),
) -> UiSettingsResponse:
    row = await _get_or_create_settings(session)
    await session.commit()
    return UiSettingsResponse(
        ui_language=row.ui_language,
        default_video_language=row.default_video_language,
        updated_at=row.updated_at,
    )


@router.patch("/settings/ui", response_model=UiSettingsResponse)
async def patch_ui_settings(
    payload: UiSettingsPatch,
    session: AsyncSession = Depends(get_db_session),
) -> UiSettingsResponse:
    row = await _get_or_create_settings(session)

    if payload.ui_language is not None:
        if not is_supported_language(payload.ui_language):
            from fastapi import HTTPException

            raise HTTPException(
                status_code=422,
                detail=(
                    f"ui_language {payload.ui_language!r} is not supported; "
                    f"allowed: {[l.code for l in LANGUAGES if l.enabled]}"
                ),
            )
        row.ui_language = payload.ui_language

    if payload.default_video_language is not None:
        if not is_supported_language(payload.default_video_language):
            from fastapi import HTTPException

            raise HTTPException(
                status_code=422,
                detail=(
                    f"default_video_language {payload.default_video_language!r} "
                    f"is not supported"
                ),
            )
        row.default_video_language = payload.default_video_language

    await session.commit()
    await session.refresh(row)
    return UiSettingsResponse(
        ui_language=row.ui_language,
        default_video_language=row.default_video_language,
        updated_at=row.updated_at,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/system/status
# ---------------------------------------------------------------------------


@router.get("/system/status", response_model=SystemStatusResponse)
async def get_system_status(
    session: AsyncSession = Depends(get_db_session),
) -> SystemStatusResponse:
    db_ok = True
    db_err: str | None = None
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        db_ok = False
        db_err = type(exc).__name__
    return SystemStatusResponse(
        app_name="P1.AIVideo backend",
        app_version="0.1.0",
        phase="4B",
        scope="metadata-only; no real video / lip-sync / publishing",
        server_time=datetime.now(timezone.utc),
        database_reachable=db_ok,
        database_error=db_err,
    )
