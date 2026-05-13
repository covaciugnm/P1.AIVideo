"""Pydantic schemas for the /jobs API."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from common.schemas import AudioRef, VoiceMode

from app.core.config import settings
from app.models.job import JobStatus


class JobCreateRequest(BaseModel):
    """Phase 1: metadata-only job creation request.

    No real-person assets are accepted. The four boolean confirmations are
    load-bearing — they encode operator consent + the project's compliance
    posture. All four must be `true`.
    """

    model_config = ConfigDict(extra="forbid")

    brief: str = Field(..., min_length=1, max_length=2000)
    synthetic_person_confirmed: bool
    consent_confirmed: bool
    target_duration_seconds: int = Field(default_factory=lambda: settings.target_duration_seconds)
    watermark_required: bool = True
    c2pa_required: bool = True

    # Phase 3C: voice mode + audio source.
    voice_mode: VoiceMode = "tts"
    script_text: str | None = Field(default=None, max_length=8000)
    tts_backend: str = "piper"
    audio_ref: AudioRef | None = None

    @field_validator("synthetic_person_confirmed")
    @classmethod
    def _must_be_synthetic(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("synthetic_person_confirmed must be true")
        return v

    @field_validator("consent_confirmed")
    @classmethod
    def _must_consent(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("consent_confirmed must be true")
        return v

    @field_validator("watermark_required")
    @classmethod
    def _watermark_required(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("watermark_required must be true")
        return v

    @field_validator("c2pa_required")
    @classmethod
    def _c2pa_required(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("c2pa_required must be true")
        return v

    @field_validator("target_duration_seconds")
    @classmethod
    def _duration_bounds(cls, v: int) -> int:
        lo, hi = settings.min_reel_duration_seconds, settings.max_reel_duration_seconds
        if not (lo <= v <= hi):
            raise ValueError(f"target_duration_seconds must be between {lo} and {hi}")
        return v

    @model_validator(mode="after")
    def _validate_voice_mode_requirements(self) -> "JobCreateRequest":
        # voice_mode="tts": script_text is required. The scriptwriter agent
        # may later REPLACE this with its own draft, but a TTS-mode job must
        # arrive at the API with a base script (Phase 3C contract).
        if self.voice_mode == "tts":
            if not self.script_text or not self.script_text.strip():
                raise ValueError(
                    "script_text is required when voice_mode='tts'"
                )

        # voice_mode="provided_audio": audio_ref is required. AudioRef's own
        # validators already enforce consent / synthetic_or_owned / mime /
        # path-safety, so we just check presence here.
        elif self.voice_mode == "provided_audio":
            if self.audio_ref is None:
                raise ValueError(
                    "audio_ref is required when voice_mode='provided_audio'"
                )

        return self


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: JobStatus
    brief: str
    target_duration_seconds: int
    watermark_required: bool
    c2pa_required: bool
    # Phase 3C voice metadata.
    voice_mode: str
    script_text: str | None = None
    tts_backend: str
    audio_ref: dict[str, Any] | None = None
    rejection_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class JobStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: JobStatus
    rejection_reason: str | None = None
