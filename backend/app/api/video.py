"""Phase 6A — video generator contract.

POST /api/v1/video/generate

Metadata-only. No real video, no GPU, no model loading. The endpoint:

1. Validates that the job, image artifact, audio artifact, and (optional)
   edit_plan artifact exist and have the right types.
2. Resolves the requested video provider against the static catalog.
3. Returns a ``not_implemented`` / ``not_configured`` result.

Real inference is wired in a later phase. The schemas are stable so
agents/orchestrator/dag can pre-fetch them once the lipsync stage is
ready to receive structured input.
"""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.models.artifact import Artifact
from app.models.job import Job

router = APIRouter(prefix="/api/v1/video", tags=["video"])


_KNOWN_VIDEO_PROVIDERS = {"sadtalker", "musetalk", "wav2lip"}


VideoStatus = Literal[
    "accepted",
    "not_configured",
    "missing_inputs",
    "failed",
    "completed",
    "not_implemented",
]


class VideoGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: uuid.UUID
    image_artifact_id: uuid.UUID
    audio_artifact_id: uuid.UUID
    provider_id: str = Field(default="sadtalker", max_length=80)
    model_id: str | None = Field(default=None, max_length=160)
    target_duration_seconds: int = Field(..., ge=1, le=600)
    edit_plan_artifact_id: uuid.UUID | None = None
    metadata: dict = Field(default_factory=dict)


class VideoGenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: VideoStatus
    provider_id: str
    model_id: str | None = None
    job_id: uuid.UUID
    output_video_artifact_id: uuid.UUID | None = None
    error_code: str | None = None
    message: str = ""
    metadata: dict = Field(default_factory=dict)


@router.post(
    "/generate",
    response_model=VideoGenerationResult,
)
async def video_generate(
    payload: VideoGenerationRequest,
    session: AsyncSession = Depends(get_db_session),
) -> VideoGenerationResult:
    # 1. Job exists.
    job_row = await session.execute(select(Job).where(Job.id == payload.job_id))
    if job_row.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="job not found")

    # 2. Image artifact exists + correct type.
    img_row = await session.execute(
        select(Artifact).where(Artifact.id == payload.image_artifact_id)
    )
    img = img_row.scalar_one_or_none()
    if img is None:
        return VideoGenerationResult(
            status="missing_inputs",
            provider_id=payload.provider_id,
            model_id=payload.model_id,
            job_id=payload.job_id,
            error_code="image_artifact_not_found",
            message=f"image artifact {payload.image_artifact_id} not found",
        )
    if img.artifact_type != "image":
        return VideoGenerationResult(
            status="missing_inputs",
            provider_id=payload.provider_id,
            model_id=payload.model_id,
            job_id=payload.job_id,
            error_code="wrong_image_artifact_type",
            message=f"artifact {payload.image_artifact_id} is type {img.artifact_type!r}, expected 'image'",
        )

    # 3. Audio artifact exists + correct type.
    aud_row = await session.execute(
        select(Artifact).where(Artifact.id == payload.audio_artifact_id)
    )
    aud = aud_row.scalar_one_or_none()
    if aud is None:
        return VideoGenerationResult(
            status="missing_inputs",
            provider_id=payload.provider_id,
            model_id=payload.model_id,
            job_id=payload.job_id,
            error_code="audio_artifact_not_found",
            message=f"audio artifact {payload.audio_artifact_id} not found",
        )
    if aud.artifact_type != "audio":
        return VideoGenerationResult(
            status="missing_inputs",
            provider_id=payload.provider_id,
            model_id=payload.model_id,
            job_id=payload.job_id,
            error_code="wrong_audio_artifact_type",
            message=f"artifact {payload.audio_artifact_id} is type {aud.artifact_type!r}, expected 'audio'",
        )

    # 4. Optional edit_plan artifact validation.
    if payload.edit_plan_artifact_id is not None:
        ep_row = await session.execute(
            select(Artifact).where(Artifact.id == payload.edit_plan_artifact_id)
        )
        ep = ep_row.scalar_one_or_none()
        if ep is None:
            return VideoGenerationResult(
                status="missing_inputs",
                provider_id=payload.provider_id,
                model_id=payload.model_id,
                job_id=payload.job_id,
                error_code="edit_plan_artifact_not_found",
                message=f"edit_plan artifact {payload.edit_plan_artifact_id} not found",
            )
        if ep.artifact_type != "edit_plan":
            return VideoGenerationResult(
                status="missing_inputs",
                provider_id=payload.provider_id,
                model_id=payload.model_id,
                job_id=payload.job_id,
                error_code="wrong_edit_plan_artifact_type",
                message=f"artifact {payload.edit_plan_artifact_id} is type {ep.artifact_type!r}, expected 'edit_plan'",
            )

    # 5. Provider exists in the catalog.
    if payload.provider_id not in _KNOWN_VIDEO_PROVIDERS:
        return VideoGenerationResult(
            status="not_configured",
            provider_id=payload.provider_id,
            model_id=payload.model_id,
            job_id=payload.job_id,
            error_code="unknown_provider",
            message=(
                f"video provider {payload.provider_id!r} is not in the known "
                f"catalog ({sorted(_KNOWN_VIDEO_PROVIDERS)})."
            ),
        )

    # 6. All providers are placeholders today. Real inference is wired in
    # a later phase. We return ``not_implemented`` with the request shape
    # echoed back so the operator sees the contract is in place.
    return VideoGenerationResult(
        status="not_implemented",
        provider_id=payload.provider_id,
        model_id=payload.model_id,
        job_id=payload.job_id,
        error_code="provider_not_implemented",
        message=(
            f"video provider {payload.provider_id!r} is a Phase 3A stub; "
            "real inference + GPU integration land in a later phase. "
            "Inputs validated; no MP4 produced."
        ),
        metadata={
            "image_artifact_id": str(payload.image_artifact_id),
            "audio_artifact_id": str(payload.audio_artifact_id),
            "edit_plan_artifact_id": (
                str(payload.edit_plan_artifact_id)
                if payload.edit_plan_artifact_id is not None
                else None
            ),
            "target_duration_seconds": payload.target_duration_seconds,
            "image_dims": [img.width, img.height] if img.width else None,
            "audio_duration_seconds": aud.duration_seconds,
        },
    )
