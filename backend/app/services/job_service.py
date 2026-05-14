"""Job service — DB writes for /jobs endpoints."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobStatus
from app.schemas.job import JobCreateRequest
from app.services.queue_publisher import publish_job_created


async def create_job(session: AsyncSession, payload: JobCreateRequest) -> Job:
    # Audio + image refs are stored as plain JSON dicts in the DB — never binary.
    audio_ref_dict = (
        payload.audio_ref.model_dump(mode="json")
        if payload.audio_ref is not None
        else None
    )
    image_ref_dict = (
        payload.image_ref.model_dump(mode="json")
        if payload.image_ref is not None
        else None
    )
    job = Job(
        brief=payload.brief,
        target_duration_seconds=payload.target_duration_seconds,
        synthetic_person_confirmed=payload.synthetic_person_confirmed,
        consent_confirmed=payload.consent_confirmed,
        watermark_required=payload.watermark_required,
        c2pa_required=payload.c2pa_required,
        voice_mode=payload.voice_mode,
        script_text=payload.script_text,
        tts_backend=payload.tts_backend,
        audio_ref=audio_ref_dict,
        face_mode=payload.face_mode,
        image_ref=image_ref_dict,
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


TERMINAL_STATUSES = {JobStatus.published, JobStatus.rejected, JobStatus.failed}

# Fields that are safe to edit any time before the job is in a terminal
# state.
_PRE_TERMINAL_FIELDS = frozenset({"brief", "target_duration_seconds"})

# Fields that are only safe to edit while the job is still in
# ``pending_compliance`` — once policy_gate has run, these have been
# consumed by later stages.
_PRE_COMPLIANCE_FIELDS = frozenset(
    {
        "script_text",
        "voice_mode",
        "face_mode",
        "tts_backend",
        "watermark_required",
        "c2pa_required",
    }
)


class JobEditError(Exception):
    """Raised when an update violates the editable-field policy."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


async def update_job(
    session: AsyncSession,
    job_id: uuid.UUID,
    patch: dict,
) -> Job | None:
    """Apply a metadata-only patch.

    Returns the updated job, or None if not found. Raises :class:`JobEditError`
    on policy violations (terminal-state edit, immutable-field edit).
    """
    job = await get_job(session, job_id)
    if job is None:
        return None
    # Filter out unset/None fields — patch shape.
    fields = {k: v for k, v in patch.items() if v is not None}
    if not fields:
        return job  # no-op

    if job.status in TERMINAL_STATUSES:
        raise JobEditError(
            status_code=409,
            detail=f"job is in terminal state {job.status.value}; no edits accepted",
        )

    # If the job has moved past pending_compliance, refuse to mutate fields
    # later stages may have already consumed.
    if job.status != JobStatus.pending_compliance:
        violators = sorted(_PRE_COMPLIANCE_FIELDS & fields.keys())
        if violators:
            raise JobEditError(
                status_code=409,
                detail=(
                    f"job is past pending_compliance ({job.status.value}); "
                    f"fields are no longer editable: {', '.join(violators)}"
                ),
            )

    # Apply the patch.
    for key, value in fields.items():
        if key in _PRE_TERMINAL_FIELDS or key in _PRE_COMPLIANCE_FIELDS:
            setattr(job, key, value)
        else:
            # Shouldn't happen — caller is the PATCH handler whose schema
            # restricts the keys — but defensive: refuse silently rather
            # than overwrite a sensitive column.
            raise JobEditError(
                status_code=400,
                detail=f"field {key!r} is not editable",
            )
    await session.commit()
    await session.refresh(job)
    return job


async def delete_job(session: AsyncSession, job_id: uuid.UUID) -> bool:
    """Delete the job row.

    Stage runs + compliance events + artifacts cascade via the FK
    ``ON DELETE CASCADE``. Artifact local_path files on disk are NOT
    removed — that's a separate concern handled by retention sweeps and
    deliberately not coupled to API-level delete. Returns True on success,
    False if the job didn't exist.
    """
    job = await get_job(session, job_id)
    if job is None:
        return False
    await session.delete(job)
    await session.commit()
    return True
