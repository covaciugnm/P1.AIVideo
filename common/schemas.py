"""Shared Pydantic schemas.

These are the metadata envelopes that cross stage boundaries. They never
carry binary payloads — only references (URIs, hashes, IDs).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from common.enums import ProviderHealthStatus, StageName
from common.path_safety import validate_local_audio_path


class AssetSpec(BaseModel):
    """Declaration of a file a provider needs at load time.

    Used by ``LipSyncProvider.required_assets()`` and
    ``VoiceProvider.required_assets()``. Phase 3A only checks file
    *existence*; sha256 verification lands in Phase 3B.
    """

    model_config = ConfigDict(extra="forbid")

    relative_path: str          # relative to the provider's models_root
    description: str = ""       # human-readable
    sha256: str | None = None   # expected checksum (verified in Phase 3B)
    size_bytes: int | None = None
    source_url: str | None = None  # documentation only; never auto-fetched
    license_note: str = ""


class ProviderHealth(BaseModel):
    """Structured result of a provider ``healthcheck()`` call."""

    model_config = ConfigDict(extra="forbid")

    backend: str
    status: ProviderHealthStatus
    models_root: str | None = None
    missing_assets: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class ArtifactRef(BaseModel):
    """Reference to an artifact in object storage.

    Metadata only — `uri` points at MinIO/S3. No bytes are carried in
    queue messages, DB rows, or agent state.
    """

    model_config = ConfigDict(extra="forbid")

    kind: str  # "image" | "audio" | "video" | "json" | "text"
    uri: str  # e.g. "s3://aivideo-jobs/{job_uuid}/portrait.png"
    sha256: str | None = None
    size_bytes: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class StageOutput(BaseModel):
    """Standard return shape for every stage handler."""

    model_config = ConfigDict(extra="forbid")

    artifacts: dict[str, ArtifactRef] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""
    noop: bool = True


AudioRefType = Literal["local_path", "artifact_uri"]
AudioMimeType = Literal["audio/wav", "audio/x-wav"]
VoiceMode = Literal["tts", "provided_audio"]


class AudioRef(BaseModel):
    """Reference to an operator-supplied audio file (Phase 3C).

    Carried as METADATA — neither the API nor the queue ever loads the
    actual audio bytes. The voice handler (or a downstream stage) reads
    the file when it actually needs it.

    Compliance fields are load-bearing:

    - ``consent_confirmed`` must be ``True`` — the operator asserts they
      have lawful authority to use this recording.
    - ``synthetic_or_owned_voice`` must be ``True`` — the recording is
      either synthetic or a voice the operator owns/has rights to. Voice
      cloning of a third party is **never** allowed (no Phase 3C path
      enables it, and the schema refuses anything but ``True`` here).

    Path safety (``type="local_path"`` only) is enforced via
    ``common.path_safety.validate_local_audio_path``.
    """

    model_config = ConfigDict(extra="forbid")

    type: AudioRefType
    path: str
    mime_type: AudioMimeType
    duration_seconds: float | None = None
    checksum: str | None = None  # operator-supplied sha256 hex, optional
    consent_confirmed: bool
    synthetic_or_owned_voice: bool

    @field_validator("consent_confirmed")
    @classmethod
    def _must_consent(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("audio_ref.consent_confirmed must be true")
        return v

    @field_validator("synthetic_or_owned_voice")
    @classmethod
    def _must_be_synthetic_or_owned(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError(
                "audio_ref.synthetic_or_owned_voice must be true "
                "(voice cloning of others is not allowed)"
            )
        return v

    @model_validator(mode="after")
    def _validate_path_for_type(self) -> "AudioRef":
        if self.type == "local_path":
            validate_local_audio_path(self.path)
        else:
            # artifact_uri — must look like a URI scheme (s3://, file://, ...)
            if "://" not in self.path:
                raise ValueError(
                    "audio_ref.path with type='artifact_uri' must be a URI "
                    f"(e.g. 's3://bucket/key.wav'); got: {self.path!r}"
                )
        return self


class ComplianceTokenClaims(BaseModel):
    """Claims carried inside a `compliance_token`. See pre_lipsync_auth."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    synthetic_person_confirmed: bool
    consent_confirmed: bool
    watermark_required: bool
    c2pa_required: bool
    allowed_lipsync_backend: str
    issued_at: datetime
    expires_at: datetime
    phase: str = "phase2_noop"
    issued_by: str = "pre_lipsync_auth"


class DagState(BaseModel):
    """In-memory state passed between DAG stages.

    The runner mutates this object as stages complete. It is never
    persisted directly — durable state lives in `jobs` + `stage_runs` rows.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    job_id: uuid.UUID
    brief: str
    target_duration_seconds: int
    synthetic_person_confirmed: bool
    consent_confirmed: bool
    watermark_required: bool
    c2pa_required: bool

    # Phase 3C: voice mode + optional provided-audio reference.
    voice_mode: VoiceMode = "tts"
    script_text: str | None = None
    tts_backend: str = "piper"
    audio_ref: AudioRef | None = None

    # Accumulated stage outputs (keyed by stage id).
    stage_outputs: dict[str, StageOutput] = Field(default_factory=dict)

    # Compliance token, set by the pre_lipsync_auth stage.
    compliance_token: str | None = None

    # Tracking
    completed_stages: list[str] = Field(default_factory=list)
    rejected: bool = False
    rejection_reason: str | None = None
    rejected_at_stage: StageName | None = None
