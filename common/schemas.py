"""Shared Pydantic schemas.

These are the metadata envelopes that cross stage boundaries. They never
carry binary payloads — only references (URIs, hashes, IDs).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from common.enums import StageName


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

    # Accumulated stage outputs (keyed by stage id).
    stage_outputs: dict[str, StageOutput] = Field(default_factory=dict)

    # Compliance token, set by the pre_lipsync_auth stage.
    compliance_token: str | None = None

    # Tracking
    completed_stages: list[str] = Field(default_factory=list)
    rejected: bool = False
    rejection_reason: str | None = None
    rejected_at_stage: StageName | None = None
