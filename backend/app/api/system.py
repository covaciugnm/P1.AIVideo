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
        accepted_audio_mime_types=["audio/wav", "audio/x-wav", "audio/wave"],
        accepted_image_mime_types=["image/png", "image/jpeg", "image/webp"],
        accepted_audio_extensions=[".wav"],
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
