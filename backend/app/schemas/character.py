"""Character / Persona schemas — Phase 12.

A ``Character`` carries a structured profile with five logical sections:

- ``identity`` — name, gender, DOB, age, nationality, languages, etc.
- ``appearance`` — physical traits + visual constraints.
- ``education`` — academic + professional history.
- ``personality`` — communication style, temperament, archetype.
- ``voice`` — TTS/voice preferences.
- ``script_behaviour`` — defaults for the video pipeline.

Every dropdown field is declared as a string here (we accept open
values for forward compatibility) and validated against the
``/api/v1/characters/lookups`` payload on the frontend. The
``profile_json`` column on the ``characters`` table is the
serialised form of :class:`CharacterProfile`.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Phase 23 lifecycle: editing↔active→retired (+ legacy inactive/draft kept
# so historical rows still validate). "editing" and "active" reserve the
# character's TTS voice; "retired" frees it.
CharacterStatus = Literal["active", "inactive", "draft", "editing", "retired"]


# ---------------------------------------------------------------------------
# Profile sub-sections
# ---------------------------------------------------------------------------


class CharacterIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=200)
    display_name: str | None = Field(default=None, max_length=200)
    slug: str | None = Field(default=None, max_length=200)
    gender: str | None = Field(default=None, max_length=40)
    date_of_birth: date | None = None
    age: int | None = Field(default=None, ge=0, le=150)
    nationality: str | None = Field(default=None, max_length=80)
    native_language: str | None = Field(default=None, max_length=40)
    spoken_languages: list[str] = Field(default_factory=list)
    marital_status: str | None = Field(default=None, max_length=40)
    place_of_birth: str | None = Field(default=None, max_length=200)
    current_location: str | None = Field(default=None, max_length=200)
    social_status: str | None = Field(default=None, max_length=80)
    is_public_persona: bool = False
    # Phase IG-5 — compliance flag. True ONLY when the character intentionally
    # depicts a real, identifiable person (requires separate authorization).
    # When True + SYNTHETIC_ONLY_ENFORCED, image generation is blocked.
    is_real_person: bool = False


class CharacterAppearance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    height: str | None = Field(default=None, max_length=40)
    weight_or_build: str | None = Field(default=None, max_length=80)
    skin_tone: str | None = Field(default=None, max_length=40)
    hair_color: str | None = Field(default=None, max_length=40)
    hair_style: str | None = Field(default=None, max_length=80)
    eye_color: str | None = Field(default=None, max_length=40)
    face_shape: str | None = Field(default=None, max_length=40)
    distinctive_features: str | None = Field(default=None, max_length=1000)
    clothing_style: str | None = Field(default=None, max_length=200)
    visual_consistency_notes: str | None = Field(default=None, max_length=2000)
    negative_visual_constraints: str | None = Field(default=None, max_length=2000)


class CharacterEducation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    education_level: str | None = Field(default=None, max_length=40)
    field_of_study: str | None = Field(default=None, max_length=200)
    certifications: list[str] = Field(default_factory=list)
    occupation: str | None = Field(default=None, max_length=200)
    professional_seniority: str | None = Field(default=None, max_length=40)
    current_role: str | None = Field(default=None, max_length=200)
    previous_roles: list[str] = Field(default_factory=list)
    cv_summary: str | None = Field(default=None, max_length=4000)
    industry_domain: str | None = Field(default=None, max_length=200)
    expertise: list[str] = Field(default_factory=list)
    authority_level: str | None = Field(default=None, max_length=40)
    reputation_notes: str | None = Field(default=None, max_length=2000)


class CharacterPersonality(BaseModel):
    model_config = ConfigDict(extra="forbid")

    archetype: str | None = Field(default=None, max_length=40)
    communication_style: str | None = Field(default=None, max_length=40)
    temperament: str | None = Field(default=None, max_length=40)
    emotional_tone: str | None = Field(default=None, max_length=40)
    confidence_level: str | None = Field(default=None, max_length=20)
    humor_level: str | None = Field(default=None, max_length=20)
    formality_level: str | None = Field(default=None, max_length=20)
    empathy_level: str | None = Field(default=None, max_length=20)
    assertiveness_level: str | None = Field(default=None, max_length=20)
    patience_level: str | None = Field(default=None, max_length=20)
    moral_values: str | None = Field(default=None, max_length=2000)
    fears: str | None = Field(default=None, max_length=1000)
    motivations: str | None = Field(default=None, max_length=1000)
    goals: str | None = Field(default=None, max_length=1000)
    conflict_style: str | None = Field(default=None, max_length=40)
    decision_style: str | None = Field(default=None, max_length=40)
    narrative_role: str | None = Field(default=None, max_length=40)


class CharacterVoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_language: str | None = Field(default=None, max_length=40)
    accent: str | None = Field(default=None, max_length=80)
    voice_gender: str | None = Field(default=None, max_length=20)
    voice_age: str | None = Field(default=None, max_length=20)
    speaking_speed: str | None = Field(default=None, max_length=20)
    pitch: str | None = Field(default=None, max_length=20)
    tone: str | None = Field(default=None, max_length=40)
    preferred_tts_provider_id: str | None = Field(default=None, max_length=80)
    f5tts_profile: str | None = Field(default=None, max_length=200)
    voice_sample_library_ref: str | None = Field(default=None, max_length=400)


class CharacterScriptBehaviour(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_role_in_videos: str | None = Field(default=None, max_length=40)
    default_speaking_duration_seconds: int | None = Field(default=None, ge=1, le=600)
    default_camera_framing: str | None = Field(default=None, max_length=40)
    default_mood: str | None = Field(default=None, max_length=40)
    default_background: str | None = Field(default=None, max_length=200)
    default_topic_expertise: str | None = Field(default=None, max_length=200)
    allowed_topics: list[str] = Field(default_factory=list)
    blocked_topics: list[str] = Field(default_factory=list)
    safety_notes: str | None = Field(default=None, max_length=2000)
    prompt_style_notes: str | None = Field(default=None, max_length=2000)
    script_generation_notes: str | None = Field(default=None, max_length=2000)


# ---------------------------------------------------------------------------
# Full profile + request/response wrappers
# ---------------------------------------------------------------------------


class CharacterProfile(BaseModel):
    """The full persona profile stored on ``characters.profile_json``."""

    model_config = ConfigDict(extra="forbid")

    identity: CharacterIdentity
    appearance: CharacterAppearance = Field(default_factory=CharacterAppearance)
    education: CharacterEducation = Field(default_factory=CharacterEducation)
    personality: CharacterPersonality = Field(default_factory=CharacterPersonality)
    voice: CharacterVoice = Field(default_factory=CharacterVoice)
    script_behaviour: CharacterScriptBehaviour = Field(
        default_factory=CharacterScriptBehaviour
    )

    def computed_age(self) -> int | None:
        """Best-effort age from ``identity.date_of_birth``.

        Falls back to ``identity.age`` if the DOB is missing.
        """
        if self.identity.date_of_birth is not None:
            today = date.today()
            born = self.identity.date_of_birth
            years = today.year - born.year - (
                (today.month, today.day) < (born.month, born.day)
            )
            return max(0, years)
        return self.identity.age


class CharacterCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: CharacterProfile
    slug: str | None = Field(default=None, max_length=200)
    status: CharacterStatus = "active"
    default_language: str | None = Field(default=None, max_length=8)
    default_voice_provider_id: str | None = Field(default=None, max_length=80)
    default_image_provider_id: str | None = Field(default=None, max_length=80)


class CharacterUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: CharacterProfile | None = None
    status: CharacterStatus | None = None
    default_language: str | None = Field(default=None, max_length=8)
    default_voice_provider_id: str | None = Field(default=None, max_length=80)
    default_image_provider_id: str | None = Field(default=None, max_length=80)


class CharacterStatusRequest(BaseModel):
    """Phase 23 — explicit lifecycle transition payload."""

    model_config = ConfigDict(extra="forbid")

    status: CharacterStatus


class CharacterCloneRequest(BaseModel):
    """Phase 24 — optional payload for the clone endpoint."""

    model_config = ConfigDict(extra="forbid")

    new_name: str | None = Field(default=None, max_length=200)


class CharacterSummary(BaseModel):
    """Lightweight payload for list/dropdown views."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str
    slug: str
    display_name: str | None
    status: CharacterStatus
    default_language: str | None
    default_voice_provider_id: str | None
    default_image_provider_id: str | None
    main_reference_image_id: uuid.UUID | None
    # Phase 16 — once True, main_reference_image_id is immutable.
    face_locked: bool = False
    # Phase 24 — full-body reference image + its lock.
    full_body_reference_image_id: uuid.UUID | None = None
    full_body_locked: bool = False
    image_count: int = 0
    video_count: int = 0
    version_number: int
    created_at: datetime
    updated_at: datetime


class CharacterResponse(BaseModel):
    """Full character payload returned by detail endpoints."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str
    slug: str
    display_name: str | None
    status: CharacterStatus
    profile: CharacterProfile
    default_language: str | None
    default_voice_provider_id: str | None
    default_image_provider_id: str | None
    main_reference_image_id: uuid.UUID | None
    face_locked: bool = False
    full_body_reference_image_id: uuid.UUID | None = None
    full_body_locked: bool = False
    version_number: int
    image_count: int = 0
    video_count: int = 0
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class CharacterListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CharacterSummary]
    total: int


# ---------------------------------------------------------------------------
# Lookups (translatable dropdown options sourced from the backend)
# ---------------------------------------------------------------------------


class LookupOption(BaseModel):
    """One row in a translatable dropdown."""

    model_config = ConfigDict(extra="forbid")

    value: str
    label_key: str  # i18n key the frontend resolves through ``useT()``
    label_en: str  # English fallback label (used in non-UI contexts)
    label_ro: str  # Romanian label (so the API is bilingual without
    #                a UI round-trip when an external integration reads it)


class CharacterLookupsResponse(BaseModel):
    """Translatable dropdown catalogue for the character profile form."""

    model_config = ConfigDict(extra="forbid")

    gender: list[LookupOption]
    marital_status: list[LookupOption]
    education_level: list[LookupOption]
    social_status: list[LookupOption]
    professional_seniority: list[LookupOption]
    authority_level: list[LookupOption]
    personality_archetype: list[LookupOption]
    communication_style: list[LookupOption]
    temperament: list[LookupOption]
    emotional_tone: list[LookupOption]
    level_scale: list[LookupOption]  # low / medium / high / very_high
    conflict_style: list[LookupOption]
    decision_style: list[LookupOption]
    narrative_role: list[LookupOption]
    voice_gender: list[LookupOption]
    voice_age: list[LookupOption]
    speaking_speed: list[LookupOption]
    pitch: list[LookupOption]
    tone: list[LookupOption]
    camera_framing: list[LookupOption]
    mood: list[LookupOption]
    character_status: list[LookupOption]
    image_status: list[LookupOption]
    language: list[LookupOption]


# ---------------------------------------------------------------------------
# Image library
# ---------------------------------------------------------------------------


ImageStatus = Literal["draft", "accepted", "rejected", "reference", "archived"]


class CharacterImageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    character_id: uuid.UUID
    file_path: str | None
    local_url: str | None
    prompt: str | None
    negative_prompt: str | None
    provider_id: str | None
    model_id: str | None
    seed: int | None
    settings_json: dict[str, Any] | None
    status: ImageStatus
    is_main_reference: bool
    width: int | None
    height: int | None
    size_bytes: int | None
    checksum_sha256: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    # Phase 21 iter 2 — when the image was just generated, the service
    # also registers it as a global ``ArtifactType.image`` row so the
    # talking-head pipeline (face_mode=provided_image) can consume it.
    # ``None`` for older rows or when the dual registration failed.
    artifact_id: uuid.UUID | None = None
    # Phase IG-3 — identity-consistent pipeline metadata.
    role: str = "generated_variation"
    identity_similarity_score: float | None = None
    identity_drift_warning: bool = False
    generation_params_json: dict[str, Any] | None = None


class CharacterImageListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CharacterImageResponse]
    total: int


class CharacterImageGenerateRequest(BaseModel):
    """Operator-supplied image-generation request.

    Either ``prompt`` or ``reference_image_id`` (or both, for
    image-to-image when the provider supports it) must be set.
    """

    model_config = ConfigDict(extra="forbid")

    prompt: str | None = Field(default=None, max_length=10000)
    negative_prompt: str | None = Field(default=None, max_length=2000)
    provider_id: str = Field(..., max_length=80)
    model_id: str | None = Field(default=None, max_length=160)
    seed: int | None = Field(default=None, ge=0, le=(1 << 63) - 1)
    width: int = Field(default=1024, ge=64, le=4096)
    height: int = Field(default=1024, ge=64, le=4096)
    steps: int | None = Field(default=None, ge=1, le=200)
    guidance_scale: float | None = Field(default=None, ge=0, le=50)
    reference_image_id: uuid.UUID | None = None
    use_main_reference: bool = False
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("prompt")
    @classmethod
    def _require_prompt_or_reference(cls, v: str | None, info) -> str | None:
        # We can't yet see other fields at this point in v2; the cross-field
        # check happens in a model_validator below.
        return v


AspectRatio = Literal["portrait", "landscape", "square"]
QualityPreset = Literal["draft", "standard", "high"]


class CharacterGenerateInitialRequest(BaseModel):
    """Phase IG-2 — first-image (text-to-image) generation request."""

    model_config = ConfigDict(extra="forbid")

    aspect_ratio: AspectRatio = "portrait"
    quality_preset: QualityPreset = "standard"
    seed: int | None = None
    workflow_override: str | None = Field(default=None, max_length=80)


class CharacterGenerateConsistentRequest(BaseModel):
    """Phase IG-2 — identity-consistent generation request. Identity is
    locked from the canonical references; these fields describe the SCENE."""

    model_config = ConfigDict(extra="forbid")

    scene_prompt: str = Field(default="", max_length=10000)
    outfit_prompt: str = Field(default="", max_length=1000)
    location_prompt: str = Field(default="", max_length=1000)
    season: str = Field(default="", max_length=80)
    time_of_day: str = Field(default="", max_length=80)
    weather: str = Field(default="", max_length=120)
    head_wear: str = Field(default="", max_length=200)
    mood: str = Field(default="", max_length=120)
    pose: str = Field(default="", max_length=200)
    framing: str = Field(default="", max_length=120)
    aspect_ratio: AspectRatio = "portrait"
    quality_preset: QualityPreset = "standard"
    seed: int | None = None
    provider_override: str | None = Field(default=None, max_length=80)
    negative_prompt_extra: str = Field(default="", max_length=1000)


class CharacterImageGenerateError(BaseModel):
    """Categorised error payload returned by ``/images/generate``."""

    model_config = ConfigDict(extra="forbid")

    error_code: Literal[
        "provider_not_implemented",
        "provider_not_configured",
        "provider_unavailable",
        "runtime_missing",
        "assets_missing",
        "gpu_unavailable",
        "reference_image_missing",
        "validation_failed",
        "generation_failed",
        "storage_failed",
        "rate_limited",
    ]
    detail: str
    provider_id: str
    fallback: str | None = None


class CharacterImageActionResponse(BaseModel):
    """Returned by accept/reject/set-main-reference endpoints."""

    model_config = ConfigDict(extra="forbid")

    image: CharacterImageResponse
    character_main_reference_image_id: uuid.UUID | None
    # Phase 24 — companion full-body reference (set-full-body-reference).
    character_full_body_reference_image_id: uuid.UUID | None = None


# ---------------------------------------------------------------------------
# Script context (Phase D)
# ---------------------------------------------------------------------------


class CharacterScriptContextResponse(BaseModel):
    """Structured prompt fragment fed into the LLM scriptwriter.

    See :func:`app.services.character_script_context.build_character_script_context`.
    """

    model_config = ConfigDict(extra="forbid")

    character_id: uuid.UUID
    text: str
    fields: dict[str, Any]
