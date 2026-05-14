"""Read-only response schemas for the Phase 4A job-view API endpoints.

These models exist so the future web UI has a stable, typed contract to
consume. Every field is **metadata only** — never bytes, never large
binary payloads. The artifacts table never carried media in the first
place (everything was references + checksums), so this layer just
re-exposes those rows + the stage_runs / compliance_events tables in a
shape that's ergonomic for the UI.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from common.enums import ComplianceDecisionType, JobStatus


class JobSummary(BaseModel):
    """One row in the GET /jobs list response."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    status: JobStatus
    brief: str
    target_duration_seconds: int
    voice_mode: str
    face_mode: str | None = None
    created_at: datetime
    updated_at: datetime
    current_stage: str | None = None
    progress_percent: float
    artifact_count: int


class StageProgress(BaseModel):
    """Per-stage progress info embedded in JobProgress."""

    model_config = ConfigDict(extra="forbid")

    stage_name: str
    status: str  # one of common.enums.StageStatus values, or "pending" if not started
    started_at: datetime | None = None
    completed_at: datetime | None = None


class JobProgress(BaseModel):
    """GET /jobs/{id}/progress — aggregate view across the canonical DAG."""

    model_config = ConfigDict(extra="forbid")

    job_id: uuid.UUID
    status: JobStatus
    total_stages: int
    completed_stages: int
    failed_stages: int
    current_stage: str | None = None
    progress_percent: float
    stages: list[StageProgress]


class StageTimelineEntry(BaseModel):
    """GET /jobs/{id}/timeline — one row per stage_run."""

    model_config = ConfigDict(extra="forbid")

    stage_name: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = None
    error_message: str | None = None
    artifact_refs: list[str]
    metadata_summary: dict[str, Any]


class ArtifactResponse(BaseModel):
    """GET /jobs/{id}/artifacts — metadata-only artifact row.

    The ``metadata_json`` field passes through whatever the producing
    stage wrote (structured_script, edit_plan, qc_report, final_export,
    etc.). It is JSON-serializable by construction — every artifact
    handler in Phases 3D–3J stores only references + small structured
    metadata, never bytes.
    """

    model_config = ConfigDict(extra="forbid")

    artifact_id: uuid.UUID
    artifact_type: str
    uri: str
    mime_type: str | None = None
    checksum_sha256: str | None = None
    size_bytes: int | None = None
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    sample_rate: int | None = None
    channels: int | None = None
    local_path: str | None = None
    created_at: datetime
    stage_run_id: uuid.UUID | None = None
    metadata_summary: dict[str, Any]


class ComplianceEventApiResponse(BaseModel):
    """GET /jobs/{id}/compliance-events — one row per ComplianceEvent."""

    model_config = ConfigDict(extra="forbid")

    event_type: str  # the compliance gate (policy_gate / identity_guard / ...)
    decision: ComplianceDecisionType
    reasons: list[str]
    created_at: datetime
    metadata_summary: dict[str, Any]


class QCReportResponse(BaseModel):
    """GET /jobs/{id}/qc-report — the structured QC report.

    The body is the same dict the QC handler stored under
    ``Artifact.metadata_json["qc_report"]``. We expose it as a typed
    response with a clearly-named field so the future UI can switch on
    it without guessing.
    """

    model_config = ConfigDict(extra="forbid")

    job_id: uuid.UUID
    artifact_id: uuid.UUID
    artifact_uri: str
    checksum_sha256: str | None = None
    qc_report: dict[str, Any]
    created_at: datetime


class FinalExportResponse(BaseModel):
    """GET /jobs/{id}/final-export — the structured FinalExport manifest."""

    model_config = ConfigDict(extra="forbid")

    job_id: uuid.UUID
    artifact_id: uuid.UUID
    artifact_uri: str
    checksum_sha256: str | None = None
    final_export: dict[str, Any]
    created_at: datetime
