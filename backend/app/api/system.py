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
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
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


# ---------------------------------------------------------------------------
# GET /api/v1/system/technical-architecture
#
# Phase 12T — serve docs/TECHNICAL_ARCHITECTURE.md so the frontend
# "Technical Help" page can render and search it. Pure read; no auth needed
# (same surface as /healthz).
# ---------------------------------------------------------------------------


class TechnicalArchitectureResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    source_path: str
    size_bytes: int
    markdown: str
    generated_at: datetime


_TECH_ARCH_CANDIDATES = (
    Path("/app/docs/TECHNICAL_ARCHITECTURE.md"),
    Path(__file__).resolve().parents[3] / "docs" / "TECHNICAL_ARCHITECTURE.md",
)


def _resolve_tech_arch_path() -> Path | None:
    for candidate in _TECH_ARCH_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


@router.get(
    "/system/technical-architecture",
    response_model=TechnicalArchitectureResponse,
)
async def get_technical_architecture() -> TechnicalArchitectureResponse:
    path = _resolve_tech_arch_path()
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="TECHNICAL_ARCHITECTURE.md not bundled with this image",
        )
    text_md = path.read_text(encoding="utf-8")
    return TechnicalArchitectureResponse(
        title="Technical Architecture — P1.AIVideo",
        source_path=str(path),
        size_bytes=len(text_md.encode("utf-8")),
        markdown=text_md,
        generated_at=datetime.now(timezone.utc),
    )


@router.get(
    "/system/technical-architecture.md",
    response_class=Response,
    responses={200: {"content": {"text/markdown": {}}}},
)
async def get_technical_architecture_markdown() -> Response:
    path = _resolve_tech_arch_path()
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="TECHNICAL_ARCHITECTURE.md not bundled with this image",
        )
    return Response(
        content=path.read_bytes(),
        media_type="text/markdown; charset=utf-8",
    )


# ---------------------------------------------------------------------------
# Phase 13 — backend log ring buffer endpoint
#
# Returns the latest backend-side log lines so the right-sidebar
# "Backend" tab can poll for progress events that the in-browser bus
# never sees (orchestrator dispatches, DB writes, secret loads,
# character image generations, etc.).
# ---------------------------------------------------------------------------


class BackendLogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: int
    ts: float
    level: str
    logger: str
    message: str
    extra: dict[str, Any] = {}


class BackendLogsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latest_seq: int
    server_time: datetime
    entries: list[BackendLogEntry]


class WrapperStatusItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    container: str
    base_url: str
    reachable: bool
    status: str | None = None
    ready: bool | None = None
    error: str | None = None


class WrapperStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    server_time: datetime
    items: list[WrapperStatusItem]


# Hostnames + standard internal port (8080) for the model-* wrappers.
# Backend lives in the same Docker network so the names resolve.
_WRAPPERS = [
    ("sdxl", "aivideo-model-sdxl-1", 8080),
    ("flux", "aivideo-model-flux-1", 8080),
    ("sd35", "aivideo-model-sd35-1", 8080),
    ("comfyui", "aivideo-model-comfyui-1", 8080),
    ("a1111", "aivideo-model-a1111-1", 8080),
    ("sadtalker", "aivideo-model-sadtalker-1", 8080),
    ("wav2lip", "aivideo-model-wav2lip-1", 8080),
    ("musetalk", "aivideo-model-musetalk-1", 8080),
    ("liveportrait", "aivideo-model-liveportrait-1", 8080),
    ("echomimic", "aivideo-model-echomimic-1", 8080),
    ("hallo", "aivideo-model-hallo-1", 8080),
    ("svd", "aivideo-model-svd-1", 8080),
    ("animatediff", "aivideo-model-animatediff-1", 8080),
    ("ltx_video", "aivideo-model-ltx-1", 8080),
    ("hunyuan_video", "aivideo-model-hunyuanvideo-1", 8080),
    ("mochi", "aivideo-model-mochi-1", 8080),
    ("tts_ro", "aivideo-model-tts-ro-1", 8080),
]


@router.get(
    "/system/wrappers",
    response_model=WrapperStatusResponse,
)
async def get_wrapper_status() -> WrapperStatusResponse:
    """Phase 15E — live probe every model-* wrapper /health endpoint.

    Frontend uses this to render green/yellow/red badges next to each
    provider in the dropdown, so the operator never picks a provider
    whose container is stopped or unhealthy.
    """
    import asyncio
    import json
    import logging
    import socket

    logger = logging.getLogger(__name__)

    async def _probe(name: str, host: str, port: int) -> WrapperStatusItem:
        url = f"http://{host}:{port}/health"
        loop = asyncio.get_event_loop()

        def _do() -> tuple[bool, str | None, bool | None, str | None]:
            import urllib.request
            try:
                socket.gethostbyname(host)
            except OSError as exc:
                return False, None, None, f"dns_fail: {exc}"
            try:
                with urllib.request.urlopen(url, timeout=2.0) as r:
                    payload = json.loads(r.read())
                return True, payload.get("status"), bool(payload.get("ready")), None
            except Exception as exc:  # noqa: BLE001
                return False, None, None, f"{type(exc).__name__}: {exc}"

        ok, status, ready, err = await loop.run_in_executor(None, _do)
        return WrapperStatusItem(
            name=name, container=host, base_url=f"http://{host}:{port}",
            reachable=ok, status=status, ready=ready, error=err,
        )

    items = await asyncio.gather(*[_probe(n, h, p) for n, h, p in _WRAPPERS])
    logger.info(
        "system.wrappers.probe ready=%d offline=%d",
        sum(1 for i in items if i.reachable and i.ready),
        sum(1 for i in items if not i.reachable),
    )
    return WrapperStatusResponse(
        server_time=datetime.now(timezone.utc),
        items=list(items),
    )


@router.get(
    "/system/logs/backend",
    response_model=BackendLogsResponse,
)
async def get_backend_logs(
    since_seq: int | None = None,
    limit: int = 200,
) -> BackendLogsResponse:
    """Snapshot of the backend's in-memory log buffer.

    Pass ``since_seq=<last-seen-seq>`` to receive only newer entries.
    Default ``limit=200`` keeps payloads modest for a polling sidebar.
    """
    from app.core.log_buffer import get_buffer

    if limit < 1:
        limit = 1
    if limit > 1000:
        limit = 1000
    buffer = get_buffer()
    items = buffer.snapshot(since_seq=since_seq, limit=limit)
    return BackendLogsResponse(
        latest_seq=buffer.latest_seq(),
        server_time=datetime.now(timezone.utc),
        entries=[
            BackendLogEntry(
                seq=r.seq,
                ts=r.ts,
                level=r.level,
                logger=r.logger,
                message=r.message,
                extra=r.extra,
            )
            for r in items
        ],
    )
