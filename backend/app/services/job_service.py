"""Job service — DB writes for /jobs endpoints."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobStatus
from app.schemas.job import JobCreateRequest
from app.services.queue_publisher import publish_job_created


async def create_job(session: AsyncSession, payload: JobCreateRequest) -> Job:
    job = Job(
        brief=payload.brief,
        target_duration_seconds=payload.target_duration_seconds,
        synthetic_person_confirmed=payload.synthetic_person_confirmed,
        consent_confirmed=payload.consent_confirmed,
        watermark_required=payload.watermark_required,
        c2pa_required=payload.c2pa_required,
        status=JobStatus.pending_compliance,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    await publish_job_created(job)
    return job


async def get_job(session: AsyncSession, job_id: uuid.UUID) -> Job | None:
    result = await session.execute(select(Job).where(Job.id == job_id))
    return result.scalar_one_or_none()


async def set_job_status(
    session: AsyncSession,
    job_id: uuid.UUID,
    status: JobStatus,
    rejection_reason: str | None = None,
) -> Job | None:
    job = await get_job(session, job_id)
    if job is None:
        return None
    job.status = status
    if rejection_reason is not None:
        job.rejection_reason = rejection_reason
    await session.commit()
    await session.refresh(job)
    return job
