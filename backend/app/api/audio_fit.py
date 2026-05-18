"""Phase 5C — audio fit-check.

POST /api/v1/audio/fit-check

Compares an audio artifact's actual duration against the target reel
duration and returns:

- ``fit_status``: ``ok`` / ``too_short`` / ``too_long`` / ``missing_audio``
- ``recommendation``: ``accept`` / ``regenerate_script_shorter`` /
  ``regenerate_script_longer`` / ``adjust_target_duration`` /
  ``upload_better_audio``
- ``delta_seconds``: actual − target

Metadata-only — no Whisper, no transcription, no model inference. Reads
``duration_seconds`` from the audio artifact row, which Phase 3D/4F
already populates from the WAV validator (and, for converted MP3 etc.,
from ffprobe on the converted PCM WAV).
"""
from __future__ import annotations

import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

logger = logging.getLogger(__name__)
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.models.artifact import Artifact
from app.models.job import Job

router = APIRouter(prefix="/api/v1/audio", tags=["audio"])


# Tolerance windows. These mirror what an operator would visually accept:
# under 1 s off is "ok"; up to 3 s short is "regenerate slightly longer";
# beyond that, recommend stronger action.
_OK_WINDOW_SECONDS = 1.0
_SOFT_WINDOW_SECONDS = 3.0


FitStatus = Literal["ok", "too_short", "too_long", "missing_audio"]
Recommendation = Literal[
    "accept",
    "regenerate_script_shorter",
    "regenerate_script_longer",
    "adjust_target_duration",
    "upload_better_audio",
]


class FitCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: uuid.UUID | None = None
    script_text: str | None = Field(default=None, max_length=8000)
    audio_artifact_id: uuid.UUID | None = None
    target_duration_seconds: int | None = Field(default=None, ge=1, le=600)

    @model_validator(mode="after")
    def _validate_inputs(self) -> "FitCheckRequest":
        if self.job_id is None and self.target_duration_seconds is None:
            raise ValueError(
                "either job_id or target_duration_seconds must be provided"
            )
        return self


class FitCheckResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_duration_seconds: int
    audio_duration_seconds: float | None
    delta_seconds: float | None
    fit_status: FitStatus
    recommendation: Recommendation
    audio_artifact_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    metadata: dict


def _classify(target: int, audio: float | None) -> tuple[FitStatus, Recommendation, float | None]:
    if audio is None:
        return "missing_audio", "upload_better_audio", None
    delta = round(audio - target, 3)
    abs_delta = abs(delta)
    if abs_delta <= _OK_WINDOW_SECONDS:
        return "ok", "accept", delta
    if delta < 0:
        # Audio is shorter than target.
        if abs_delta <= _SOFT_WINDOW_SECONDS:
            return "too_short", "regenerate_script_longer", delta
        return "too_short", "adjust_target_duration", delta
    # Audio is longer than target.
    if abs_delta <= _SOFT_WINDOW_SECONDS:
        return "too_long", "regenerate_script_shorter", delta
    return "too_long", "adjust_target_duration", delta


@router.post("/fit-check", response_model=FitCheckResponse)
async def audio_fit_check(
    payload: FitCheckRequest,
    session: AsyncSession = Depends(get_db_session),
) -> FitCheckResponse:
    logger.info(
        "audio.fit_check.start job_id=%s audio_artifact=%s target_dur=%s",
        payload.job_id, payload.audio_artifact_id, payload.target_duration_seconds,
    )
    # Resolve target duration.
    target = payload.target_duration_seconds
    job_id: uuid.UUID | None = payload.job_id
    if job_id is not None:
        job_row = await session.execute(select(Job).where(Job.id == job_id))
        job = job_row.scalar_one_or_none()
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        if target is None:
            target = job.target_duration_seconds

    if target is None:
        raise HTTPException(
            status_code=400,
            detail="target_duration_seconds could not be resolved",
        )

    # Resolve audio duration from the explicit artifact id if provided,
    # otherwise from the most recent audio artifact belonging to the job.
    audio_artifact_id = payload.audio_artifact_id
    audio_duration: float | None = None
    sample_rate: int | None = None
    channels: int | None = None

    if audio_artifact_id is not None:
        art_row = await session.execute(
            select(Artifact).where(Artifact.id == audio_artifact_id)
        )
        art = art_row.scalar_one_or_none()
        if art is None:
            raise HTTPException(
                status_code=404, detail=f"audio artifact {audio_artifact_id} not found"
            )
        if art.artifact_type != "audio":
            raise HTTPException(
                status_code=400,
                detail=f"artifact {audio_artifact_id} is type {art.artifact_type!r}, expected 'audio'",
            )
        audio_duration = art.duration_seconds
        sample_rate = art.sample_rate
        channels = art.channels
    elif job_id is not None:
        # Pick the most recent audio artifact for this job.
        art_row = await session.execute(
            select(Artifact)
            .where(Artifact.job_id == job_id, Artifact.artifact_type == "audio")
            .order_by(Artifact.created_at.desc())
        )
        art = art_row.scalars().first()
        if art is not None:
            audio_artifact_id = art.id
            audio_duration = art.duration_seconds
            sample_rate = art.sample_rate
            channels = art.channels

    fit_status, recommendation, delta = _classify(target, audio_duration)

    metadata = {
        "ok_window_seconds": _OK_WINDOW_SECONDS,
        "soft_window_seconds": _SOFT_WINDOW_SECONDS,
        "sample_rate": sample_rate,
        "channels": channels,
        "script_length_chars": len(payload.script_text) if payload.script_text else None,
    }
    return FitCheckResponse(
        target_duration_seconds=target,
        audio_duration_seconds=audio_duration,
        delta_seconds=delta,
        fit_status=fit_status,
        recommendation=recommendation,
        audio_artifact_id=audio_artifact_id,
        job_id=job_id,
        metadata=metadata,
    )
