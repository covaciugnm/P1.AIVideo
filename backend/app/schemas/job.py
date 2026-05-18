"""Pydantic schemas for the /jobs API."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from common.schemas import AudioRef, FaceMode, ImageRef, VoiceMode

from app.core.config import settings
from app.core.languages import (
    DEFAULT_SUBTITLE_FORMAT,
    DEFAULT_VIDEO_LANGUAGE,
    SUPPORTED_SUBTITLE_FORMATS,
    is_supported_language,
    is_supported_subtitle_format,
    language_codes,
)
from app.models.job import JobStatus
from app.schemas.providers import ProviderSelection


def _validate_language_code(v: str | None) -> str | None:
    if v is None:
        return v
    if not is_supported_language(v):
        raise ValueError(
            f"language code {v!r} is not supported; allowed: {list(language_codes())}"
        )
    return v


def _validate_subtitle_format(v: str | None) -> str | None:
    if v is None:
        return v
    if not is_supported_subtitle_format(v):
        raise ValueError(
            f"subtitle_format must be one of {list(SUPPORTED_SUBTITLE_FORMATS)}"
        )
    return v


def _validate_subtitle_languages(v: list[str] | None) -> list[str] | None:
    if v is None:
        return v
    if not isinstance(v, list):
        raise ValueError("subtitle_languages must be a list of language codes")
    seen: set[str] = set()
    out: list[str] = []
    for code in v:
        if not is_supported_language(code):
            raise ValueError(
                f"subtitle language {code!r} is not supported; allowed: {list(language_codes())}"
            )
        if code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out


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

    # Phase 3E: face mode + image source. ``face_mode`` is optional (no
    # default) so jobs created before Phase 3E (and Phase 1–3D tests)
    # don't need an image_ref. When face_mode="provided_image" is set
    # explicitly, image_ref is required and validated.
    face_mode: FaceMode | None = None
    image_ref: ImageRef | None = None

    # Phase 4F: optional per-job provider selection.
    provider_selection: ProviderSelection | None = None

    # Phase 12 — optional persona binding. ``character_id`` references a
    # row in ``characters``; the job_service snapshots the profile at
    # submit time onto ``character_snapshot`` so subsequent edits or
    # soft-deletes of the character never rewrite history.
    character_id: uuid.UUID | None = None

    # Phase 11A: language + subtitle metadata. All have safe defaults so
    # pre-11A payloads stay valid; the model_validator below normalises
    # subtitle_languages when subtitle_enabled=True but no list given.
    video_language: str = Field(default=DEFAULT_VIDEO_LANGUAGE, max_length=8)
    subtitle_enabled: bool = False
    subtitle_languages: list[str] | None = None
    subtitle_format: str = Field(default=DEFAULT_SUBTITLE_FORMAT, max_length=8)
    subtitle_burn_in: bool = False
    transcript_language: str | None = Field(default=None, max_length=8)

    _validate_video_language = field_validator("video_language")(
        classmethod(lambda cls, v: _validate_language_code(v))
    )
    _validate_transcript_language = field_validator("transcript_language")(
        classmethod(lambda cls, v: _validate_language_code(v))
    )
    _validate_subtitle_format_fn = field_validator("subtitle_format")(
        classmethod(lambda cls, v: _validate_subtitle_format(v))
    )
    _validate_subtitle_languages_fn = field_validator("subtitle_languages")(
        classmethod(lambda cls, v: _validate_subtitle_languages(v))
    )

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

        # Phase 3E: face_mode="provided_image" requires image_ref. ImageRef
        # already validates consent + synthetic_person + mime + path-safety.
        if self.face_mode == "provided_image":
            if self.image_ref is None:
                raise ValueError(
                    "image_ref is required when face_mode='provided_image'"
                )

        # Phase 11A: if subtitles are enabled but no language list was sent,
        # default to ``[video_language]`` so the operator can flip a single
        # checkbox without thinking about codes. Empty-list inputs get the
        # same treatment for symmetry.
        if self.subtitle_enabled and not self.subtitle_languages:
            object.__setattr__(self, "subtitle_languages", [self.video_language])

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
    # Phase 3E face metadata.
    face_mode: str | None = None
    image_ref: dict[str, Any] | None = None
    # Phase 4F per-job provider selection.
    provider_selection: dict[str, Any] | None = None
    rejection_reason: str | None = None
    # Phase 8D: operational recovery metadata (cancel timestamps, retry
    # counter, last categorised error). Optional so older clients keep
    # working without code changes.
    recovery_metadata: dict[str, Any] | None = None
    # Phase 11A — language + subtitle metadata. Defaults match the model
    # so jobs created before this phase deserialize cleanly.
    video_language: str = DEFAULT_VIDEO_LANGUAGE
    subtitle_enabled: bool = False
    subtitle_languages: list[str] | None = None
    subtitle_format: str = DEFAULT_SUBTITLE_FORMAT
    subtitle_burn_in: bool = False
    transcript_language: str | None = None
    # Phase 12 — character binding + frozen snapshot.
    character_id: uuid.UUID | None = None
    character_snapshot: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    # Phase 11B — editability hints derived from job.status. Lets the UI
    # decide whether to render Edit / Retry buttons and which form
    # fields to disable without re-deriving the policy client-side.
    can_edit: bool = True
    can_retry: bool = False
    locked_fields: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _populate_edit_policy(self) -> "JobResponse":
        # Import here to avoid a circular import (job_service ← job model
        # ← this schema).
        from app.services.job_service import compute_edit_policy

        can_edit, can_retry, locked = compute_edit_policy(self.status)
        object.__setattr__(self, "can_edit", can_edit)
        object.__setattr__(self, "can_retry", can_retry)
        object.__setattr__(self, "locked_fields", list(locked))
        return self


class JobStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: JobStatus
    rejection_reason: str | None = None


class JobUpdateRequest(BaseModel):
    """Phase 4E: metadata-only patch.

    Every field is optional; only the fields included in the request body are
    applied. The handler refuses to mutate **immutable** fields (voice_mode,
    face_mode, script_text, audio_ref/image_ref, the four compliance
    booleans) once the job has progressed past ``pending_compliance``, since
    later stages may have already consumed them. ``brief`` and
    ``target_duration_seconds`` stay editable until the job reaches a
    terminal state (``published`` / ``rejected`` / ``failed``).
    """

    model_config = ConfigDict(extra="forbid")

    brief: str | None = Field(default=None, min_length=1, max_length=2000)
    target_duration_seconds: int | None = None
    script_text: str | None = Field(default=None, max_length=8000)
    voice_mode: VoiceMode | None = None
    face_mode: FaceMode | None = None
    tts_backend: str | None = Field(default=None, max_length=32)
    watermark_required: bool | None = None
    c2pa_required: bool | None = None
    provider_selection: ProviderSelection | None = None
    # Phase 11E — when SadTalker rejects a job with
    # ``video_face_landmark_missing`` or ``video_face_image_too_small``,
    # the operator-recovery flow needs to replace the portrait. We
    # accept a UUID pointing at an existing ``image`` artifact rather
    # than a full ImageRef so the UI only has to forward the upload's
    # ``artifact_id``. The PATCH handler resolves the artifact and
    # rewrites the persisted ``image_ref`` in place.
    image_artifact_id: uuid.UUID | None = None
    # Phase 11A — language + subtitle patch surface. All optional.
    video_language: str | None = Field(default=None, max_length=8)
    subtitle_enabled: bool | None = None
    subtitle_languages: list[str] | None = None
    subtitle_format: str | None = Field(default=None, max_length=8)
    subtitle_burn_in: bool | None = None
    transcript_language: str | None = Field(default=None, max_length=8)

    _validate_video_language = field_validator("video_language")(
        classmethod(lambda cls, v: _validate_language_code(v))
    )
    _validate_transcript_language = field_validator("transcript_language")(
        classmethod(lambda cls, v: _validate_language_code(v))
    )
    _validate_subtitle_format_fn = field_validator("subtitle_format")(
        classmethod(lambda cls, v: _validate_subtitle_format(v))
    )
    _validate_subtitle_languages_fn = field_validator("subtitle_languages")(
        classmethod(lambda cls, v: _validate_subtitle_languages(v))
    )

    @field_validator("target_duration_seconds")
    @classmethod
    def _duration_bounds(cls, v: int | None) -> int | None:
        if v is None:
            return v
        lo, hi = settings.min_reel_duration_seconds, settings.max_reel_duration_seconds
        if not (lo <= v <= hi):
            raise ValueError(f"target_duration_seconds must be between {lo} and {hi}")
        return v

    @field_validator("watermark_required")
    @classmethod
    def _watermark_required(cls, v: bool | None) -> bool | None:
        if v is None:
            return v
        if v is not True:
            raise ValueError("watermark_required must be true")
        return v

    @field_validator("c2pa_required")
    @classmethod
    def _c2pa_required(cls, v: bool | None) -> bool | None:
        if v is None:
            return v
        if v is not True:
            raise ValueError("c2pa_required must be true")
        return v

    def has_any_field(self) -> bool:
        return any(v is not None for v in self.model_dump().values())
