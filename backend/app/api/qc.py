"""Phase 8C — on-demand real media QC.

POST /api/v1/qc/inspect

Takes a job_id + an artifact_id (or auto-picks the most recent
final_export / video artifact for the job), runs the deterministic
media-QC pipeline (`backend/app/services/media_qc.py`) against the
on-disk file, and returns a structured report.

Operator-triggered. Does **not** mutate the Phase 3I DAG QC report —
it produces a fresh on-demand result the frontend can render alongside
the metadata-only QC card.

Safety boundary mirrors Phase 8A / 8B:

- Artifact must exist.
- ``artifact_type`` must be ``video`` or ``final_export``.
- ``local_path`` must resolve to a real file under an allowed root
  (uploads + artifacts root). 403 on outside-roots.
- Path traversal symbols rejected before resolve.
- The service never raises; ffprobe is bounded.

No ML, no GPU, no model weights.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.enums import ArtifactType

from app.core.config import settings
from app.core.deps import get_db_session
from app.models.artifact import Artifact
from app.models.job import Job
from app.services.media_qc import inspect_media_artifact

router = APIRouter(prefix="/api/v1/qc", tags=["qc"])


_INSPECTABLE_ARTIFACT_TYPES = frozenset(
    {ArtifactType.video.value, ArtifactType.final_export.value}
)


class QcInspectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: uuid.UUID
    artifact_id: uuid.UUID | None = None
    require_audio: bool = Field(default=False)
    expected_duration_seconds: float | None = None


class QcInspectResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["completed", "missing_inputs", "not_configured"]
    job_id: uuid.UUID
    artifact_id: uuid.UUID | None = None
    artifact_type: str | None = None
    error_code: str | None = None
    message: str = ""
    report: dict | None = None


def _allowed_roots() -> list[Path]:
    out: list[Path] = []
    for env_name, default in (
        ("UPLOAD_AUDIO_ROOT", settings.upload_audio_root),
        ("UPLOAD_IMAGE_ROOT", settings.upload_image_root),
        ("UPLOAD_TEXT_ROOT", settings.upload_text_root),
        ("ARTIFACTS_LOCAL_ROOT", settings.artifacts_local_root),
    ):
        raw = os.environ.get(env_name, default)
        if raw:
            out.append(Path(raw).resolve(strict=False))
    return out


def _path_is_under_allowed_root(p: Path) -> bool:
    for root in _allowed_roots():
        try:
            p.relative_to(root)
            return True
        except ValueError:
            continue
    return False


async def _resolve_target_artifact(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    explicit_id: uuid.UUID | None,
) -> tuple[Artifact | None, str | None]:
    if explicit_id is not None:
        row = await session.execute(select(Artifact).where(Artifact.id == explicit_id))
        art = row.scalar_one_or_none()
        if art is None:
            return None, "artifact_not_found"
        if art.artifact_type not in _INSPECTABLE_ARTIFACT_TYPES:
            return None, "wrong_artifact_type"
        return art, None

    # Prefer final_export over video — operators usually want to
    # validate the packaged export when it exists.
    for art_type in (ArtifactType.final_export.value, ArtifactType.video.value):
        row = await session.execute(
            select(Artifact)
            .where(
                Artifact.job_id == job_id,
                Artifact.artifact_type == art_type,
            )
            .order_by(desc(Artifact.created_at))
            .limit(1)
        )
        art = row.scalar_one_or_none()
        if art is not None:
            return art, None
    return None, "media_artifact_missing"


@router.post("/inspect", response_model=QcInspectResult)
async def qc_inspect(
    payload: QcInspectRequest,
    session: AsyncSession = Depends(get_db_session),
) -> QcInspectResult:
    job_row = await session.execute(select(Job).where(Job.id == payload.job_id))
    if job_row.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="job not found")

    art, err = await _resolve_target_artifact(
        session, job_id=payload.job_id, explicit_id=payload.artifact_id
    )
    if err is not None or art is None:
        return QcInspectResult(
            status="missing_inputs",
            job_id=payload.job_id,
            artifact_id=payload.artifact_id,
            error_code=err,
            message=(
                "no video or final_export artifact for this job"
                if err == "media_artifact_missing"
                else f"artifact rejected: {err}"
            ),
        )

    if not art.local_path:
        return QcInspectResult(
            status="missing_inputs",
            job_id=payload.job_id,
            artifact_id=art.id,
            artifact_type=art.artifact_type,
            error_code="artifact_no_local_path",
            message="artifact row has no on-disk file",
        )

    if ".." in art.local_path.split(os.sep):
        return QcInspectResult(
            status="not_configured",
            job_id=payload.job_id,
            artifact_id=art.id,
            artifact_type=art.artifact_type,
            error_code="unsafe_artifact_path",
            message="artifact local_path looks unsafe",
        )

    try:
        resolved = Path(art.local_path).resolve(strict=True)
    except FileNotFoundError:
        return QcInspectResult(
            status="missing_inputs",
            job_id=payload.job_id,
            artifact_id=art.id,
            artifact_type=art.artifact_type,
            error_code="artifact_file_missing",
            message="artifact file is not on disk",
        )

    if not _path_is_under_allowed_root(resolved):
        return QcInspectResult(
            status="not_configured",
            job_id=payload.job_id,
            artifact_id=art.id,
            artifact_type=art.artifact_type,
            error_code="artifact_outside_allowed_roots",
            message="artifact path is outside allowed roots",
        )

    expected_duration = payload.expected_duration_seconds
    if expected_duration is None:
        # Fall back to the job's target duration so the duration-delta
        # check has something to compare against.
        job_row2 = await session.execute(select(Job).where(Job.id == payload.job_id))
        job = job_row2.scalar_one()
        expected_duration = float(job.target_duration_seconds)

    report = inspect_media_artifact(
        path=resolved,
        mime_type=art.mime_type,
        expected_duration_seconds=expected_duration,
        expected_checksum_sha256=art.checksum_sha256,
        require_audio=payload.require_audio,
    )

    return QcInspectResult(
        status="completed",
        job_id=payload.job_id,
        artifact_id=art.id,
        artifact_type=art.artifact_type,
        message=(
            f"media qc {'passed' if report.passed else 'failed'} "
            f"({len(report.checks)} checks, "
            f"{len(report.warnings)} warnings, "
            f"{len(report.failures)} failures)"
        ),
        report=report.to_dict(),
    )
