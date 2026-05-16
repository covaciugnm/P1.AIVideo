"""/jobs endpoints.

Phase 1: POST /jobs + GET /jobs/{id}.
Phase 4A: add the read-only view endpoints the future web UI needs —
list, progress, timeline, artifacts, compliance events, QC report,
final export. Every response is metadata-only; no binary content is
exposed.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.enums import CANONICAL_DAG_STAGES, JobStatus, StageStatus

from app.core.deps import get_db_session
from app.models.artifact import Artifact
from app.models.compliance import ComplianceEvent
from app.models.job import Job
from app.models.stage_run import StageRun
from app.schemas.job import JobCreateRequest, JobResponse, JobUpdateRequest
from app.schemas.job_views import (
    ArtifactResponse,
    ComplianceEventApiResponse,
    FinalExportResponse,
    JobDetail,
    JobFullSummary,
    JobProgress,
    JobSummary,
    QCReportResponse,
    StageProgress,
    StageTimelineEntry,
)
from app.services import job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_progress_stats(
    stage_runs: list[StageRun],
) -> tuple[int, int, int, str | None]:
    """Return (completed, failed, total, current_stage)."""
    total = len(CANONICAL_DAG_STAGES)
    completed_names = {r.stage for r in stage_runs if r.status == StageStatus.succeeded}
    failed_names = {
        r.stage for r in stage_runs if r.status in (StageStatus.failed, StageStatus.rejected)
    }
    running = next((r.stage for r in stage_runs if r.status == StageStatus.running), None)

    if running is not None:
        current = running
    elif failed_names:
        # First failed/rejected stage in canonical order is the "current" one
        # the operator should look at.
        current = next((s for s in CANONICAL_DAG_STAGES if s in failed_names), None)
    elif len(completed_names) >= total:
        current = None  # job fully done
    else:
        current = next((s for s in CANONICAL_DAG_STAGES if s not in completed_names), None)

    return len(completed_names), len(failed_names), total, current


async def _load_job_or_404(session: AsyncSession, job_id: uuid.UUID) -> Job:
    job = await job_service.get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


async def _stage_runs_for_job(session: AsyncSession, job_id: uuid.UUID) -> list[StageRun]:
    result = await session.execute(
        select(StageRun).where(StageRun.job_id == job_id).order_by(StageRun.started_at)
    )
    return list(result.scalars().all())


async def _artifact_count_for_job(session: AsyncSession, job_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count(Artifact.id)).where(Artifact.job_id == job_id)
    )
    return int(result.scalar_one())


async def _compliance_event_count(session: AsyncSession, job_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count(ComplianceEvent.id)).where(ComplianceEvent.job_id == job_id)
    )
    return int(result.scalar_one())


# ---------------------------------------------------------------------------
# Phase 4F-2 summary helpers
# ---------------------------------------------------------------------------


async def _latest_qc_report_dict(
    session: AsyncSession, job_id: uuid.UUID
) -> tuple[dict[str, Any] | None, Artifact | None]:
    """Return ``(qc_report_dict, artifact)`` for the most recent QC
    artifact belonging to ``job_id``, or ``(None, None)`` if no QC
    artifact exists yet.

    QC stage stores ``metadata_json['qc_report']`` on a metadata-type
    artifact (see ``agents.qc.handler``). We pull the latest one.
    """
    result = await session.execute(
        select(Artifact)
        .where(
            Artifact.job_id == job_id,
            Artifact.artifact_type == "metadata",
        )
        .order_by(Artifact.created_at.desc())
    )
    for art in result.scalars():
        qc = (art.metadata_json or {}).get("qc_report")
        if isinstance(qc, dict):
            return qc, art
    return None, None


async def _latest_final_export(
    session: AsyncSession, job_id: uuid.UUID
) -> Artifact | None:
    result = await session.execute(
        select(Artifact)
        .where(
            Artifact.job_id == job_id,
            Artifact.artifact_type == "final_export",
        )
        .order_by(Artifact.created_at.desc())
    )
    art = result.scalars().first()
    if art is None:
        return None
    manifest = (art.metadata_json or {}).get("final_export")
    if not isinstance(manifest, dict):
        return None
    return art


async def _job_to_summary(session: AsyncSession, job: Job) -> JobSummary:
    runs = await _stage_runs_for_job(session, job.id)
    completed, failed, total, current = _compute_progress_stats(runs)
    artifact_count = await _artifact_count_for_job(session, job.id)
    pct = (completed / total * 100.0) if total > 0 else 0.0

    # Phase 4F-2 booleans: derive from the existing artifact rows.
    qc_dict, _ = await _latest_qc_report_dict(session, job.id)
    qc_passed: bool | None
    if qc_dict is None:
        qc_passed = None
    else:
        passed = qc_dict.get("passed")
        qc_passed = bool(passed) if isinstance(passed, bool) else None

    final_export_art = await _latest_final_export(session, job.id)
    final_export_available = final_export_art is not None

    return JobSummary(
        id=job.id,
        status=job.status,
        brief=job.brief,
        target_duration_seconds=job.target_duration_seconds,
        voice_mode=job.voice_mode,
        face_mode=job.face_mode,
        created_at=job.created_at,
        updated_at=job.updated_at,
        current_stage=current,
        progress_percent=pct,
        artifact_count=artifact_count,
        qc_passed=qc_passed,
        final_export_available=final_export_available,
        # Phase 8F-1 — expose provider_selection on the list row so
        # dashboards can show the chosen providers without an extra
        # per-row round-trip.
        provider_selection=job.provider_selection,
        # Phase 11A — language + subtitle snapshot on the list row.
        video_language=job.video_language or "ro",
        subtitle_enabled=bool(job.subtitle_enabled),
        subtitle_languages=job.subtitle_languages,
    )


def _stage_run_to_timeline_entry(run: StageRun) -> StageTimelineEntry:
    duration_ms: int | None = None
    if run.finished_at is not None and run.started_at is not None:
        duration_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)
    metadata_summary: dict[str, Any] = {
        "noop": bool(run.noop),
    }
    if isinstance(run.extra, dict):
        if "notes" in run.extra:
            metadata_summary["notes"] = run.extra["notes"]
    return StageTimelineEntry(
        stage_name=run.stage,
        status=run.status.value,
        started_at=run.started_at,
        completed_at=run.finished_at,
        duration_ms=duration_ms,
        error_message=run.error,
        artifact_refs=list((run.artifacts or {}).keys()),
        metadata_summary=metadata_summary,
    )


def _artifact_to_response(art: Artifact) -> ArtifactResponse:
    return ArtifactResponse(
        artifact_id=art.id,
        artifact_type=art.artifact_type,
        uri=art.uri,
        mime_type=art.mime_type,
        checksum_sha256=art.checksum_sha256,
        size_bytes=art.size_bytes,
        duration_seconds=art.duration_seconds,
        width=art.width,
        height=art.height,
        sample_rate=art.sample_rate,
        channels=art.channels,
        local_path=art.local_path,
        created_at=art.created_at,
        stage_run_id=art.stage_run_id,
        metadata_summary=dict(art.metadata_json or {}),
    )


async def _stage_artifact(
    session: AsyncSession, job_id: uuid.UUID, stage: str
) -> Artifact | None:
    """Look up the most recent Artifact produced by a named stage."""
    result = await session.execute(
        select(StageRun).where(StageRun.job_id == job_id, StageRun.stage == stage)
    )
    run = result.scalars().first()
    if run is None:
        return None
    art_result = await session.execute(
        select(Artifact)
        .where(Artifact.stage_run_id == run.id)
        .order_by(Artifact.created_at)
    )
    return art_result.scalars().first()


# ---------------------------------------------------------------------------
# POST /jobs
# ---------------------------------------------------------------------------


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(
    payload: JobCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> JobResponse:
    job = await job_service.create_job(session, payload)
    return JobResponse.model_validate(job)


# ---------------------------------------------------------------------------
# GET /jobs (list)
# ---------------------------------------------------------------------------


@router.get("", response_model=list[JobSummary])
async def list_jobs(
    session: AsyncSession = Depends(get_db_session),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: JobStatus | None = Query(
        default=None,
        description="Filter by job status. Invalid values yield a 422.",
    ),
) -> list[JobSummary]:
    stmt = select(Job)
    if status is not None:
        stmt = stmt.where(Job.status == status)
    stmt = stmt.order_by(Job.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    jobs = list(result.scalars().all())
    return [await _job_to_summary(session, j) for j in jobs]


# ---------------------------------------------------------------------------
# GET /jobs/{id}  (detail — Phase 1 contract preserved)
# ---------------------------------------------------------------------------


@router.get("/{job_id}", response_model=JobDetail)
async def get_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> JobDetail:
    """Aggregate job detail (Phase 4F-2).

    The response is a superset of the original ``JobResponse`` shape:
    every legacy field is still present, plus computed pipeline +
    summary fields (``current_stage``, ``progress_percent``,
    ``artifact_count``, ``compliance_event_count``, ``latest_qc_result``,
    ``final_export_summary``). Existing clients that only read the
    legacy fields continue to work unchanged.
    """
    job = await _load_job_or_404(session, job_id)
    base = JobResponse.model_validate(job).model_dump()

    runs = await _stage_runs_for_job(session, job_id)
    completed, failed, total, current = _compute_progress_stats(runs)
    pct = (completed / total * 100.0) if total > 0 else 0.0
    artifact_count = await _artifact_count_for_job(session, job_id)
    event_count = await _compliance_event_count(session, job_id)
    qc_dict, _ = await _latest_qc_report_dict(session, job_id)
    fe_art = await _latest_final_export(session, job_id)
    fe_summary: dict[str, Any] | None = None
    if fe_art is not None:
        manifest = (fe_art.metadata_json or {}).get("final_export")
        if isinstance(manifest, dict):
            # Surface the operator-relevant headline fields; the full
            # manifest is still reachable via /final-export.
            fe_summary = {
                "passed_qc": manifest.get("passed_qc"),
                "status": manifest.get("status"),
                "disclosure_status": manifest.get("disclosure_status"),
                "watermark_required": manifest.get("watermark_required"),
                "c2pa_required": manifest.get("c2pa_required"),
                "export_uri": manifest.get("export_uri"),
            }
    return JobDetail(
        **base,
        current_stage=current,
        progress_percent=pct,
        artifact_count=artifact_count,
        compliance_event_count=event_count,
        latest_qc_result=qc_dict,
        final_export_summary=fe_summary,
    )


# ---------------------------------------------------------------------------
# PATCH /jobs/{id}   (Phase 4E)
# ---------------------------------------------------------------------------


@router.patch("/{job_id}", response_model=JobResponse)
async def update_job(
    job_id: uuid.UUID,
    payload: JobUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> JobResponse:
    if not payload.has_any_field():
        raise HTTPException(
            status_code=400, detail="no editable fields provided"
        )
    await _load_job_or_404(session, job_id)
    patch = payload.model_dump(exclude_none=True)
    if "provider_selection" in patch and payload.provider_selection is not None:
        # Persist as a plain dict, not a nested model.
        patch["provider_selection"] = payload.provider_selection.to_dict() or None
    try:
        updated = await job_service.update_job(session, job_id, patch)
    except job_service.JobEditError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JobResponse.model_validate(updated)


# ---------------------------------------------------------------------------
# DELETE /jobs/{id}  (Phase 4E)
# ---------------------------------------------------------------------------


@router.delete("/{job_id}", status_code=204)
async def delete_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    deleted = await job_service.delete_job(session, job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="job not found")


# ---------------------------------------------------------------------------
# POST /jobs/{id}/cancel + /jobs/{id}/retry  (Phase 8D)
#
# Metadata-only operational controls. Cancel marks a non-terminal job
# as rejected with an operator-cancellation reason; retry records an
# operator-requested retry on a terminal job. Neither endpoint kills an
# already-running OS process — that's a future phase. Both endpoints
# update ``jobs.recovery_metadata`` (Phase 8D JSON column) and emit a
# compliance event so the audit trail captures the decision.
# ---------------------------------------------------------------------------


from pydantic import BaseModel, ConfigDict, Field  # noqa: E402 — kept local


_TERMINAL_STATUSES = frozenset(
    {JobStatus.published, JobStatus.rejected, JobStatus.failed}
)


class JobCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=500)


class JobRetryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_name: str | None = Field(default=None, max_length=80)
    reason: str | None = Field(default=None, max_length=500)


async def _record_recovery_compliance_event(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    gate: str,
    decision: str,
    reasons: list[str],
    extra: dict[str, Any],
) -> None:
    """Phase 8D — write a compliance event for cancel / retry so the
    audit trail picks up operator actions the same way it captures
    policy / identity-guard decisions."""
    from common.enums import ComplianceDecisionType

    event = ComplianceEvent(
        job_id=job_id,
        gate=gate,
        decision=ComplianceDecisionType(decision),
        reasons=reasons,
        extra=extra,
    )
    session.add(event)
    await session.commit()


@router.post("/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(
    job_id: uuid.UUID,
    payload: JobCancelRequest,
    session: AsyncSession = Depends(get_db_session),
) -> JobResponse:
    job = await _load_job_or_404(session, job_id)
    if job.status in _TERMINAL_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(
                f"job is already terminal (status={job.status.value!r}); "
                "cancel is a no-op"
            ),
        )

    cancelled_at = datetime.now().isoformat(timespec="seconds")
    reason = payload.reason or "cancelled by operator"
    recovery = dict(job.recovery_metadata or {})
    recovery["cancelled_at"] = cancelled_at
    recovery["cancellation_reason"] = reason
    job.recovery_metadata = recovery

    job.status = JobStatus.rejected
    job.rejection_reason = f"cancelled by operator: {reason}"
    job.updated_at = datetime.now()
    await session.commit()
    await session.refresh(job)

    await _record_recovery_compliance_event(
        session,
        job_id=job.id,
        gate="job_cancel",
        decision="reject",
        reasons=[reason],
        extra={"cancelled_at": cancelled_at},
    )
    return JobResponse.model_validate(job)


@router.post("/{job_id}/retry", response_model=JobResponse)
async def retry_job(
    job_id: uuid.UUID,
    payload: JobRetryRequest,
    session: AsyncSession = Depends(get_db_session),
) -> JobResponse:
    """Mark a failed/rejected job for re-processing.

    Phase 8D recorded the operator intent in ``recovery_metadata`` and
    bumped a retry counter without changing the job status — the worker
    therefore never picked the row up again. Phase 11B closes that gap:
    after the operator has fixed the underlying cause (typically via
    PATCH /jobs/{id} on provider_selection / brief / script), Retry
    flips the status back to ``pending_compliance``, clears the stale
    ``rejection_reason``, preserves all prior stage_run rows for audit,
    and the worker re-runs the DAG with the patched metadata.
    """
    job = await _load_job_or_404(session, job_id)
    if job.status not in (JobStatus.failed, JobStatus.rejected):
        raise HTTPException(
            status_code=409,
            detail=(
                f"job is in state {job.status.value!r}; retry is only "
                "allowed for failed or rejected jobs"
            ),
        )

    requested_at = datetime.now().isoformat(timespec="seconds")
    recovery = dict(job.recovery_metadata or {})
    recovery["retry_requested_at"] = requested_at
    recovery["retry_count"] = int(recovery.get("retry_count", 0)) + 1
    # Keep the previous rejection reason so the audit trail survives,
    # but stash it under a dedicated history key.
    if job.rejection_reason:
        history = list(recovery.get("previous_rejection_reasons", []))
        history.append(job.rejection_reason)
        recovery["previous_rejection_reasons"] = history
    if payload.stage_name:
        recovery["retry_stage_name"] = payload.stage_name
    if payload.reason:
        recovery["retry_reason"] = payload.reason
    job.recovery_metadata = recovery
    # Phase 11B — re-queue the job so the orchestrator worker picks it
    # up on the next pass with the patched metadata.
    job.status = JobStatus.pending_compliance
    job.rejection_reason = None
    job.updated_at = datetime.now()
    await session.commit()
    await session.refresh(job)

    await _record_recovery_compliance_event(
        session,
        job_id=job.id,
        gate="job_retry",
        decision="accept",
        reasons=[payload.reason] if payload.reason else ["operator-requested retry"],
        extra={
            "retry_requested_at": requested_at,
            "retry_count": recovery["retry_count"],
            "retry_stage_name": payload.stage_name,
        },
    )
    return JobResponse.model_validate(job)


# ---------------------------------------------------------------------------
# GET /jobs/{id}/progress
# ---------------------------------------------------------------------------


@router.get("/{job_id}/progress", response_model=JobProgress)
async def get_job_progress(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> JobProgress:
    job = await _load_job_or_404(session, job_id)
    runs = await _stage_runs_for_job(session, job_id)
    by_stage: dict[str, StageRun] = {r.stage: r for r in runs}
    completed, failed, total, current = _compute_progress_stats(runs)
    stages = []
    for name in CANONICAL_DAG_STAGES:
        run = by_stage.get(name)
        if run is None:
            stages.append(
                StageProgress(stage_name=name, status="pending")
            )
        else:
            stages.append(
                StageProgress(
                    stage_name=name,
                    status=run.status.value,
                    started_at=run.started_at,
                    completed_at=run.finished_at,
                )
            )
    pct = (completed / total * 100.0) if total > 0 else 0.0
    # Phase 4F-2: pre-compute the flat stage-name lists so UIs don't
    # have to re-iterate the ``stages`` array client-side.
    completed_names = [s.stage_name for s in stages if s.status == "succeeded"]
    failed_names = [
        s.stage_name for s in stages if s.status in ("failed", "rejected")
    ]
    pending_names = [s.stage_name for s in stages if s.status == "pending"]
    return JobProgress(
        job_id=job.id,
        status=job.status,
        total_stages=total,
        completed_stages=completed,
        failed_stages=failed,
        current_stage=current,
        progress_percent=pct,
        stages=stages,
        pending_stages=len(pending_names),
        completed_stage_names=completed_names,
        failed_stage_names=failed_names,
        pending_stage_names=pending_names,
    )


# ---------------------------------------------------------------------------
# GET /jobs/{id}/timeline
# ---------------------------------------------------------------------------


@router.get("/{job_id}/timeline", response_model=list[StageTimelineEntry])
async def get_job_timeline(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> list[StageTimelineEntry]:
    await _load_job_or_404(session, job_id)
    runs = await _stage_runs_for_job(session, job_id)
    return [_stage_run_to_timeline_entry(r) for r in runs]


# ---------------------------------------------------------------------------
# GET /jobs/{id}/artifacts
# ---------------------------------------------------------------------------


@router.get("/{job_id}/artifacts", response_model=list[ArtifactResponse])
async def get_job_artifacts(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> list[ArtifactResponse]:
    await _load_job_or_404(session, job_id)
    result = await session.execute(
        select(Artifact)
        .where(Artifact.job_id == job_id)
        .order_by(Artifact.created_at)
    )
    return [_artifact_to_response(a) for a in result.scalars().all()]


# ---------------------------------------------------------------------------
# GET /jobs/{id}/compliance-events
# ---------------------------------------------------------------------------


@router.get(
    "/{job_id}/compliance-events", response_model=list[ComplianceEventApiResponse]
)
async def get_job_compliance_events(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> list[ComplianceEventApiResponse]:
    await _load_job_or_404(session, job_id)
    result = await session.execute(
        select(ComplianceEvent)
        .where(ComplianceEvent.job_id == job_id)
        .order_by(ComplianceEvent.created_at)
    )
    events = list(result.scalars().all())
    return [
        ComplianceEventApiResponse(
            event_type=ev.gate,
            decision=ev.decision,
            reasons=list(ev.reasons or []),
            created_at=ev.created_at,
            metadata_summary=dict(ev.extra or {}),
        )
        for ev in events
    ]


# ---------------------------------------------------------------------------
# GET /jobs/{id}/qc-report
# ---------------------------------------------------------------------------


@router.get("/{job_id}/qc-report", response_model=QCReportResponse)
async def get_job_qc_report(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> QCReportResponse:
    await _load_job_or_404(session, job_id)
    art = await _stage_artifact(session, job_id, "qc")
    if art is None:
        raise HTTPException(status_code=404, detail="qc report not available")
    qc_dict = (art.metadata_json or {}).get("qc_report")
    if not isinstance(qc_dict, dict):
        raise HTTPException(
            status_code=404,
            detail="qc artifact found but missing structured qc_report",
        )
    return QCReportResponse(
        job_id=job_id,
        artifact_id=art.id,
        artifact_uri=art.uri,
        checksum_sha256=art.checksum_sha256,
        qc_report=qc_dict,
        created_at=art.created_at,
    )


# ---------------------------------------------------------------------------
# GET /jobs/{id}/final-export
# ---------------------------------------------------------------------------


@router.get("/{job_id}/final-export", response_model=FinalExportResponse)
async def get_job_final_export(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> FinalExportResponse:
    await _load_job_or_404(session, job_id)
    # The publisher emits multiple artifacts; final_export is the typed one.
    result = await session.execute(
        select(Artifact).where(
            Artifact.job_id == job_id,
            Artifact.artifact_type == "final_export",
        ).order_by(Artifact.created_at)
    )
    art = result.scalars().first()
    if art is None:
        raise HTTPException(status_code=404, detail="final_export not available")
    manifest = (art.metadata_json or {}).get("final_export")
    if not isinstance(manifest, dict):
        raise HTTPException(
            status_code=404,
            detail="final_export artifact found but missing structured manifest",
        )
    return FinalExportResponse(
        job_id=job_id,
        artifact_id=art.id,
        artifact_uri=art.uri,
        checksum_sha256=art.checksum_sha256,
        final_export=manifest,
        created_at=art.created_at,
    )


# ---------------------------------------------------------------------------
# GET /jobs/{id}/summary  (Phase 4F-2)
# ---------------------------------------------------------------------------


@router.get("/{job_id}/summary", response_model=JobFullSummary)
async def get_job_full_summary(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> JobFullSummary:
    """Combined UI payload for a job's detail page.

    Bundles the seven individual detail endpoints into one response so
    the frontend can avoid the seven-parallel-fetch pattern when opening
    the page. The individual endpoints remain available for incremental
    polling of specific sections.

    404 if the job is unknown. ``qc_report`` and ``final_export`` stay
    ``None`` until the corresponding stage has produced its artifact.
    """
    # Detail (which 404s on its own if the job is missing).
    detail = await get_job(job_id, session)

    # Progress (already returns canonical-DAG-ordered stages + the new
    # Phase 4F-2 flat stage-name lists).
    progress = await get_job_progress(job_id, session)

    # Timeline.
    runs = await _stage_runs_for_job(session, job_id)
    timeline = [_stage_run_to_timeline_entry(r) for r in runs]

    # Artifacts (metadata only — no binary content).
    art_result = await session.execute(
        select(Artifact)
        .where(Artifact.job_id == job_id)
        .order_by(Artifact.created_at)
    )
    artifacts = [_artifact_to_response(a) for a in art_result.scalars().all()]

    # Compliance events.
    ev_result = await session.execute(
        select(ComplianceEvent)
        .where(ComplianceEvent.job_id == job_id)
        .order_by(ComplianceEvent.created_at)
    )
    events = [
        ComplianceEventApiResponse(
            event_type=ev.gate,
            decision=ev.decision,
            reasons=list(ev.reasons or []),
            created_at=ev.created_at,
            metadata_summary=dict(ev.extra or {}),
        )
        for ev in ev_result.scalars().all()
    ]

    # QC report (optional).
    qc_response: QCReportResponse | None = None
    qc_dict, qc_art = await _latest_qc_report_dict(session, job_id)
    if qc_dict is not None and qc_art is not None:
        qc_response = QCReportResponse(
            job_id=job_id,
            artifact_id=qc_art.id,
            artifact_uri=qc_art.uri,
            checksum_sha256=qc_art.checksum_sha256,
            qc_report=qc_dict,
            created_at=qc_art.created_at,
        )

    # Final export (optional).
    fe_response: FinalExportResponse | None = None
    fe_art = await _latest_final_export(session, job_id)
    if fe_art is not None:
        manifest = (fe_art.metadata_json or {}).get("final_export")
        if isinstance(manifest, dict):
            fe_response = FinalExportResponse(
                job_id=job_id,
                artifact_id=fe_art.id,
                artifact_uri=fe_art.uri,
                checksum_sha256=fe_art.checksum_sha256,
                final_export=manifest,
                created_at=fe_art.created_at,
            )

    return JobFullSummary(
        job=detail,
        progress=progress,
        timeline=timeline,
        artifacts=artifacts,
        compliance_events=events,
        qc_report=qc_response,
        final_export=fe_response,
    )
