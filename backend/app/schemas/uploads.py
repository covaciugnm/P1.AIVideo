"""Pydantic schemas for the Phase 4A-2 upload + from-inputs API."""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from common.schemas import FaceMode, VoiceMode

from app.schemas.providers import ProviderSelection


# ---------------------------------------------------------------------------
# Text upload
# ---------------------------------------------------------------------------


class UploadTextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    script_text: str = Field(..., min_length=1, max_length=64_000)
    language: str = "en"
    tone: str | None = Field(default=None, max_length=80)
    target_duration_seconds: int | None = None

    @field_validator("script_text")
    @classmethod
    def _must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("script_text must not be empty or blank")
        return v


class UploadTextResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: uuid.UUID
    artifact_type: str
    uri: str
    mime_type: str | None
    checksum_sha256: str | None
    size_bytes: int | None
    script_ref: dict[str, Any]
    metadata_summary: dict[str, Any]


# ---------------------------------------------------------------------------
# Audio upload (multipart)
# ---------------------------------------------------------------------------


class UploadAudioResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: uuid.UUID
    artifact_type: str
    uri: str
    local_path: str
    mime_type: str
    checksum_sha256: str
    size_bytes: int
    duration_seconds: float
    sample_rate: int
    channels: int
    audio_ref: dict[str, Any]
    metadata_summary: dict[str, Any]


# ---------------------------------------------------------------------------
# Image upload (multipart)
# ---------------------------------------------------------------------------


class UploadImageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: uuid.UUID
    artifact_type: str
    uri: str
    local_path: str
    mime_type: str
    checksum_sha256: str
    size_bytes: int
    width: int
    height: int
    image_ref: dict[str, Any]
    metadata_summary: dict[str, Any]


# ---------------------------------------------------------------------------
# Job creation from uploaded inputs
# ---------------------------------------------------------------------------


class JobFromInputsRequest(BaseModel):
    """Create a job by referencing previously-uploaded artifacts (or
    providing script_text inline). Compliance flags from the API stay
    mandatory; the audio + image consent flags are operator attestations
    that the UI must capture explicitly (defaults are False so accidental
    submissions can never bypass them)."""

    model_config = ConfigDict(extra="forbid")

    brief: str = Field(..., min_length=1, max_length=2000)
    target_duration_seconds: int
    synthetic_person_confirmed: bool
    consent_confirmed: bool
    watermark_required: bool = True
    c2pa_required: bool = True

    voice_mode: VoiceMode = "tts"
    face_mode: FaceMode | None = None

    script_artifact_id: uuid.UUID | None = None
    script_text: str | None = None

    audio_artifact_id: uuid.UUID | None = None
    audio_consent_confirmed: bool = False
    audio_synthetic_or_owned: bool = False

    image_artifact_id: uuid.UUID | None = None
    image_consent_confirmed: bool = False
    image_synthetic_person_confirmed: bool = False

    # Phase 8E — accept provider_selection on the upload-intake path too
    # (Phase 6D already accepts it on POST /api/v1/jobs). The frontend's
    # CreateJobForm always sends this field; without it ``extra=forbid``
    # rejected legitimate requests.
    provider_selection: ProviderSelection | None = None

    @model_validator(mode="after")
    def _validate_combinations(self) -> "JobFromInputsRequest":
        # Voice mode: either inline script_text OR a script_artifact_id (for tts);
        # audio_artifact_id (for provided_audio).
        if self.voice_mode == "tts":
            if not (self.script_text and self.script_text.strip()) and self.script_artifact_id is None:
                raise ValueError(
                    "voice_mode='tts' requires either script_text or script_artifact_id"
                )
        elif self.voice_mode == "provided_audio":
            if self.audio_artifact_id is None:
                raise ValueError(
                    "voice_mode='provided_audio' requires audio_artifact_id"
                )

        # Face mode.
        if self.face_mode == "provided_image":
            if self.image_artifact_id is None:
                raise ValueError(
                    "face_mode='provided_image' requires image_artifact_id"
                )

        return self
