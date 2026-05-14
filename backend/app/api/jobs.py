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
from app.schemas.job import JobCreateRequest, JobResponse
from app.schemas.job_views import (
    ArtifactResponse,
    ComplianceEventApiResponse,
    FinalExportResponse,
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


async def _job_to_summary(session: AsyncSession, job: Job) -> JobSummary:
    runs = await _stage_runs_for_job(session, job.id)
    completed, failed, total, current = _compute_progress_stats(runs)
    artifact_count = await _artifact_count_for_job(session, job.id)
    pct = (completed / total * 100.0) if total > 0 else 0.0
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
) -> list[JobSummary]:
    result = await session.execute(
        select(Job).order_by(Job.created_at.desc()).offset(offset).limit(limit)
    )
    jobs = list(result.scalars().all())
    return [await _job_to_summary(session, j) for j in jobs]


# ---------------------------------------------------------------------------
# GET /jobs/{id}  (detail — Phase 1 contract preserved)
# ---------------------------------------------------------------------------


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> JobResponse:
    job = await _load_job_or_404(session, job_id)
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
    return JobProgress(
        job_id=job.id,
        status=job.status,
        total_stages=total,
        completed_stages=completed,
        failed_stages=failed,
        current_stage=current,
        progress_percent=pct,
        stages=stages,
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
