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
    provider_selection_dict = (
        payload.provider_selection.to_dict()
        if payload.provider_selection is not None
        and any(payload.provider_selection.to_dict().values())
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
        provider_selection=provider_selection_dict,
        status=JobStatus.pending_compliance,
        # Phase 11A — persist language + subtitle metadata on the row.
        video_language=payload.video_language,
        subtitle_enabled=payload.subtitle_enabled,
        subtitle_languages=payload.subtitle_languages,
        subtitle_format=payload.subtitle_format,
        subtitle_burn_in=payload.subtitle_burn_in,
        transcript_language=payload.transcript_language,
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

# Phase 11B — operator-recoverable terminal states. A rejected/failed
# job is "soft terminal": the operator may still patch provider /
# script / language fields and then call /retry to re-run the DAG.
# ``published`` stays fully locked.
_RECOVERABLE_TERMINAL_STATUSES = {JobStatus.rejected, JobStatus.failed}

# Fields that are safe to edit any time before the job is in a hard
# terminal state.
_PRE_TERMINAL_FIELDS = frozenset({"brief", "target_duration_seconds"})

# Fields that are only safe to edit while the job is still in
# ``pending_compliance`` — once policy_gate has run on a still-running
# job, these have been consumed by later stages. Phase 11B re-enables
# them for ``rejected`` / ``failed`` jobs (see ``_RECOVERABLE_TERMINAL_STATUSES``)
# so the operator can fix a bad provider selection and retry.
_PRE_COMPLIANCE_FIELDS = frozenset(
    {
        "script_text",
        "voice_mode",
        "face_mode",
        "tts_backend",
        "watermark_required",
        "c2pa_required",
        "provider_selection",
        # Phase 11A — language + subtitle metadata is also pre-compliance:
        # later stages may consume the values (e.g. transcript stage uses
        # transcript_language).
        "video_language",
        "subtitle_enabled",
        "subtitle_languages",
        "subtitle_format",
        "subtitle_burn_in",
        "transcript_language",
        # Phase 11E — face image replacement on the recovery path.
        # The PATCH handler resolves ``image_artifact_id`` to an
        # existing image artifact and rewrites ``job.image_ref`` in
        # place.
        "image_artifact_id",
    }
)

ALL_EDITABLE_FIELDS = _PRE_TERMINAL_FIELDS | _PRE_COMPLIANCE_FIELDS


def compute_edit_policy(status: JobStatus) -> tuple[bool, bool, list[str]]:
    """Phase 11B — return ``(can_edit, can_retry, locked_fields)`` for a job
    at the given status. Pure function so the UI can surface the same
    flags via JobResponse and the PATCH handler can reuse the policy.

    - ``published``: fully locked — no edits, no retry.
    - ``pending_compliance``: everything editable, retry not applicable
      (the worker is about to pick it up anyway).
    - ``rejected`` / ``failed``: everything editable so the operator can
      fix a bad provider / script / language and retry; retry is the
      only path forward.
    - Any in-flight intermediate status (``accepted``, etc.): only
      ``_PRE_TERMINAL_FIELDS`` can be safely changed; pre-compliance
      fields stay locked because the running DAG may have consumed
      them.
    """
    if status == JobStatus.published:
        return False, False, sorted(ALL_EDITABLE_FIELDS)
    if status == JobStatus.pending_compliance:
        return True, False, []
    if status in _RECOVERABLE_TERMINAL_STATUSES:
        return True, True, []
    # In-flight non-terminal — only brief/duration are safe.
    return True, False, sorted(_PRE_COMPLIANCE_FIELDS)


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

    Phase 11B contract: rejected / failed jobs ARE editable so the
    operator can fix the cause (bad provider, missing script, wrong
    language) and then call /retry. Only ``published`` is fully locked.
    """
    job = await get_job(session, job_id)
    if job is None:
        return None
    # Filter out unset/None fields — patch shape.
    fields = {k: v for k, v in patch.items() if v is not None}
    if not fields:
        return job  # no-op

    can_edit, _can_retry, locked = compute_edit_policy(job.status)
    if not can_edit:
        raise JobEditError(
            status_code=409,
            detail=f"job is in terminal state {job.status.value}; no edits accepted",
        )

    locked_set = set(locked)
    if locked_set:
        violators = sorted(locked_set & fields.keys())
        if violators:
            raise JobEditError(
                status_code=409,
                detail=(
                    f"job status {job.status.value}; fields are not "
                    f"editable in this state: {', '.join(violators)}"
                ),
            )

    # Phase 11E — ``image_artifact_id`` is a logical patch field that
    # rewrites ``job.image_ref`` in place after looking up the image
    # artifact. We resolve it BEFORE the generic setattr loop and
    # remove it from the field dict so the loop doesn't try to assign
    # a ``image_artifact_id`` column on the Job model (it doesn't
    # exist; the column is ``image_ref`` JSON).
    if "image_artifact_id" in fields:
        new_image_artifact_id = fields.pop("image_artifact_id")
        from app.models.artifact import Artifact

        result = await session.execute(
            select(Artifact).where(Artifact.id == new_image_artifact_id)
        )
        image_art = result.scalar_one_or_none()
        if image_art is None:
            raise JobEditError(
                status_code=404,
                detail=(
                    f"image_artifact_id {new_image_artifact_id} not "
                    "found; upload the image first via "
                    "POST /api/v1/uploads/image"
                ),
            )
        if image_art.artifact_type != "image":
            raise JobEditError(
                status_code=422,
                detail=(
                    f"artifact {new_image_artifact_id} is type "
                    f"{image_art.artifact_type!r}, expected 'image'"
                ),
            )
        # Build the operator's ImageRef from the artifact metadata.
        # Format matches what JobCreateRequest.image_ref persists, so
        # the DAG's face stage path doesn't need a separate code path.
        new_image_ref: dict = {
            "type": "local_path",
            "path": image_art.local_path,
            "mime_type": image_art.mime_type or "image/png",
            "checksum": image_art.checksum_sha256,
            "consent_confirmed": True,
            "synthetic_person_confirmed": True,
        }
        # Preserve the original consent flags if the job already had
        # an image_ref — replacing the image doesn't re-attest consent
        # (the operator already confirmed at job-create time).
        if isinstance(job.image_ref, dict):
            for k in ("consent_confirmed", "synthetic_person_confirmed"):
                if k in job.image_ref:
                    new_image_ref[k] = job.image_ref[k]
        job.image_ref = new_image_ref

    # Apply the patch.
    for key, value in fields.items():
        if key in ALL_EDITABLE_FIELDS:
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
