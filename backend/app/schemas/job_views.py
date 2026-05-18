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

from pydantic import BaseModel, ConfigDict, Field, model_validator

from common.enums import ComplianceDecisionType, JobStatus


class JobSummary(BaseModel):
    """One row in the GET /jobs list response.

    Phase 4F-2 added ``qc_passed`` and ``final_export_available`` so the
    dashboard can render those columns without an extra round-trip per
    row.
    """

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
    # Phase 4F-2 additions. ``qc_passed`` stays ``None`` until the QC
    # stage has run; ``final_export_available`` flips True once the
    # publisher's final_export artifact lands.
    qc_passed: bool | None = None
    final_export_available: bool = False
    # Phase 8F-1 — per-job provider selection, surfaced on the list
    # endpoint so the dashboard can render the chosen providers without
    # a second round-trip per row. Nullable / optional for pre-4F jobs.
    provider_selection: dict[str, Any] | None = None
    # Phase 11A — language + subtitle highlights on the list row.
    video_language: str = "ro"
    subtitle_enabled: bool = False
    subtitle_languages: list[str] | None = None
    # Phase 11B — editability hints. Lets the Jobs List enable/disable
    # the Edit / Retry buttons per row.
    can_edit: bool = True
    can_retry: bool = False
    # Phase 12 — character binding surfaced on list rows so the dashboard
    # can show "character: Maria Popescu" or filter without a per-row
    # detail fetch.
    character_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _populate_edit_policy(self) -> "JobSummary":
        from app.services.job_service import compute_edit_policy

        can_edit, can_retry, _locked = compute_edit_policy(self.status)
        object.__setattr__(self, "can_edit", can_edit)
        object.__setattr__(self, "can_retry", can_retry)
        return self


class StageProgress(BaseModel):
    """Per-stage progress info embedded in JobProgress."""

    model_config = ConfigDict(extra="forbid")

    stage_name: str
    status: str  # one of common.enums.StageStatus values, or "pending" if not started
    started_at: datetime | None = None
    completed_at: datetime | None = None


class JobProgress(BaseModel):
    """GET /jobs/{id}/progress — aggregate view across the canonical DAG.

    Phase 4F-2 added ``pending_stages`` + three flat stage-name lists so
    a UI can render quick summaries without re-iterating ``stages``.
    """

    model_config = ConfigDict(extra="forbid")

    job_id: uuid.UUID
    status: JobStatus
    total_stages: int
    completed_stages: int
    failed_stages: int
    current_stage: str | None = None
    progress_percent: float
    stages: list[StageProgress]
    # Phase 4F-2 additions (defaulted for backward compat).
    pending_stages: int = 0
    completed_stage_names: list[str] = []
    failed_stage_names: list[str] = []
    pending_stage_names: list[str] = []


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


# ---------------------------------------------------------------------------
# Phase 4F-2: aggregate response shapes for the detail + summary endpoints.
# ---------------------------------------------------------------------------


class JobDetail(BaseModel):
    """GET /jobs/{id} — superset of the creation-time JobResponse.

    Includes every field the old ``JobResponse`` returned (so old
    clients keep working) plus computed pipeline + summary fields
    (current_stage, progress_percent, artifact_count,
    compliance_event_count, latest_qc_result, final_export_summary).
    Field order is preserved to minimise visual diffs in API consumers
    that pretty-print the response.
    """

    model_config = ConfigDict(extra="forbid")

    # JobResponse-equivalent fields.
    id: uuid.UUID
    status: JobStatus
    brief: str
    target_duration_seconds: int
    watermark_required: bool
    c2pa_required: bool
    voice_mode: str
    script_text: str | None = None
    tts_backend: str
    audio_ref: dict[str, Any] | None = None
    face_mode: str | None = None
    image_ref: dict[str, Any] | None = None
    provider_selection: dict[str, Any] | None = None
    rejection_reason: str | None = None
    # Phase 8D — operational recovery metadata. Optional so older
    # clients keep working.
    recovery_metadata: dict[str, Any] | None = None
    # Phase 11A — language + subtitle metadata.
    video_language: str = "ro"
    subtitle_enabled: bool = False
    subtitle_languages: list[str] | None = None
    subtitle_format: str = "srt"
    subtitle_burn_in: bool = False
    transcript_language: str | None = None
    # Phase 12 — character binding + frozen snapshot. Optional so
    # pre-Phase-12 jobs continue to deserialise cleanly.
    character_id: uuid.UUID | None = None
    character_snapshot: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    # Phase 4F-2 aggregate computed fields.
    current_stage: str | None = None
    progress_percent: float = 0.0
    artifact_count: int = 0
    compliance_event_count: int = 0
    latest_qc_result: dict[str, Any] | None = None
    final_export_summary: dict[str, Any] | None = None

    # Phase 11B — editability hints mirrored from JobResponse so the UI
    # can render Edit / Retry affordances directly off the detail
    # endpoint without an extra round-trip to PATCH-and-see-409.
    can_edit: bool = True
    can_retry: bool = False
    locked_fields: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _populate_edit_policy(self) -> "JobDetail":
        from app.services.job_service import compute_edit_policy

        can_edit, can_retry, locked = compute_edit_policy(self.status)
        object.__setattr__(self, "can_edit", can_edit)
        object.__setattr__(self, "can_retry", can_retry)
        object.__setattr__(self, "locked_fields", list(locked))
        return self


class JobFullSummary(BaseModel):
    """GET /jobs/{id}/summary — combined UI-friendly payload.

    Bundles the seven detail-page endpoints into one response so the
    frontend can fetch a single payload when it opens the detail view.
    Individual endpoints stay available for incremental polling.
    """

    model_config = ConfigDict(extra="forbid")

    job: JobDetail
    progress: JobProgress
    timeline: list[StageTimelineEntry]
    artifacts: list[ArtifactResponse]
    compliance_events: list[ComplianceEventApiResponse]
    qc_report: QCReportResponse | None = None
    final_export: FinalExportResponse | None = None
