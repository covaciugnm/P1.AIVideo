"""Pydantic schemas for the Phase 4A-2 upload + from-inputs API."""
from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from common.schemas import FaceMode, VoiceMode

from app.core.languages import (
    is_supported_language,
    is_supported_subtitle_format,
    language_codes,
)
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


class SceneSpec(BaseModel):
    """Phase 21 — one scene in the scenes_only / news_presenter plan.

    A scene with ``kind="presenter"`` is voiced over the character's
    still portrait with lipsync applied (mouth animated). ``kind="broll"``
    is voiced over a FLUX-rendered scene image with a Ken-Burns zoom;
    the character does not appear.
    """

    model_config = ConfigDict(extra="forbid")

    scene_number: int = Field(..., ge=1, le=99)
    kind: Literal["presenter", "broll"]
    spoken_text: str = Field(..., min_length=1, max_length=4000)
    # Required for broll scenes (it's the FLUX prompt); ignored for
    # presenter scenes (which use the character portrait).
    visual_description: str | None = Field(default=None, max_length=2000)
    # 1..20 seconds per scene per the operator pin.
    duration_s: float = Field(..., ge=1.0, le=20.0)
    # Populated by the backend after the per-scene render finishes.
    image_artifact_id: uuid.UUID | None = None
    audio_artifact_id: uuid.UUID | None = None
    clip_artifact_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _check_kind(self) -> "SceneSpec":
        if self.kind == "broll" and not (self.visual_description or "").strip():
            raise ValueError(
                "broll scene requires a non-empty visual_description"
            )
        return self


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

    # Phase 11A — language + subtitle metadata on the upload-intake path.
    # Defaults match POST /api/v1/jobs so the two routes have identical
    # acceptance criteria.
    video_language: str = Field(default="ro", max_length=8)
    subtitle_enabled: bool = False
    subtitle_languages: list[str] | None = None
    subtitle_format: str = Field(default="srt", max_length=8)
    subtitle_burn_in: bool = False
    transcript_language: str | None = Field(default=None, max_length=8)

    # Phase 12 — optional persona binding. The job_service snapshots the
    # character's profile_json onto ``jobs.character_snapshot`` at
    # submit time so subsequent edits/deletes never rewrite history.
    character_id: uuid.UUID | None = None

    # Phase 21 — pipeline variant chooser.
    #   "talking_head"  (default): single portrait + lipsync — back-compat
    #   "scenes_only"  : voiceover over B-roll scene clips (no character)
    #   "news_presenter": hybrid (presenter + B-roll interleaved)
    # The talking_head path ignores ``scene_plan``; the other two REQUIRE it.
    job_type: Literal["talking_head", "scenes_only", "news_presenter"] = "talking_head"

    # Phase 21 — operator-edited scene plan for scenes_only / news_presenter.
    # Each scene: {scene_number, kind: "presenter"|"broll", spoken_text,
    # visual_description (broll only), duration_s (1.0..20.0)}.
    scene_plan: list["SceneSpec"] | None = None

    # Phase 22 — output orientation. landscape=16:9 (default), portrait=9:16
    # (mobile reels), square=1:1.
    orientation: Literal["landscape", "portrait", "square"] = "landscape"

    @field_validator("video_language", "transcript_language")
    @classmethod
    def _check_language(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not is_supported_language(v):
            raise ValueError(
                f"language {v!r} not supported; allowed: {list(language_codes())}"
            )
        return v

    @field_validator("subtitle_format")
    @classmethod
    def _check_subtitle_format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not is_supported_subtitle_format(v):
            raise ValueError("subtitle_format must be one of srt/vtt")
        return v

    @field_validator("subtitle_languages")
    @classmethod
    def _check_subtitle_languages(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        for code in v:
            if not is_supported_language(code):
                raise ValueError(
                    f"subtitle language {code!r} not supported"
                )
        return v

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

        # Phase 21 — scene_plan invariants per job_type.
        if self.job_type in ("scenes_only", "news_presenter"):
            if not self.scene_plan:
                raise ValueError(
                    f"job_type={self.job_type!r} requires a non-empty scene_plan"
                )
            if len(self.scene_plan) > 30:
                raise ValueError(
                    f"scene_plan is too long ({len(self.scene_plan)} scenes); "
                    "max 30 to keep render time reasonable"
                )
            total = sum(s.duration_s for s in self.scene_plan)
            if total > 600:
                raise ValueError(
                    f"scene_plan total duration {total:.1f}s exceeds the "
                    "10-minute cap; trim scenes or shorten durations"
                )
            # scene_number uniqueness + ordering.
            nums = [s.scene_number for s in self.scene_plan]
            if len(set(nums)) != len(nums):
                raise ValueError("scene_plan has duplicate scene_number values")
            if self.job_type == "scenes_only":
                if any(s.kind == "presenter" for s in self.scene_plan):
                    raise ValueError(
                        "scenes_only job_type cannot contain presenter "
                        "segments — switch to news_presenter or remove them"
                    )
            elif self.job_type == "news_presenter":
                # Hybrid REQUIRES at least one presenter scene; otherwise
                # the operator probably meant scenes_only.
                if not any(s.kind == "presenter" for s in self.scene_plan):
                    raise ValueError(
                        "news_presenter requires at least one presenter "
                        "segment (use scenes_only for B-roll-only videos)"
                    )
                if self.character_id is None:
                    raise ValueError(
                        "news_presenter requires character_id (the "
                        "presenter segments use the character portrait)"
                    )
        elif self.job_type == "talking_head":
            if self.scene_plan:
                raise ValueError(
                    "talking_head job_type does not consume scene_plan — "
                    "use scenes_only or news_presenter, or drop scene_plan"
                )

        # Phase 11A: auto-populate subtitle_languages when subtitles are
        # turned on without an explicit list.
        if self.subtitle_enabled and not self.subtitle_languages:
            object.__setattr__(self, "subtitle_languages", [self.video_language])

        return self
