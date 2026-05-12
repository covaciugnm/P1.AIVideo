"""/jobs endpoints — Phase 1.

POST /jobs        Create a job. Synchronously persists + emits a job.created
                  event to the orchestrator + compliance streams.
GET  /jobs/{id}   Return the current job record.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.schemas.job import JobCreateRequest, JobResponse
from app.services import job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(
    payload: JobCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> JobResponse:
    job = await job_service.create_job(session, payload)
    return JobResponse.model_validate(job)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> JobResponse:
    job = await job_service.get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JobResponse.model_validate(job)
