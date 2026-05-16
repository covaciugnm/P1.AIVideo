"""Phase 8B — real ffmpeg final export.

POST /api/v1/export/finalize

Takes a job_id (and optionally a specific video artifact id), runs the
bounded ffmpeg remux service, and registers a real ``ArtifactType.final_export``
row pointing at the resulting MP4 on disk. Operator-triggered — the
DAG's existing publisher stage continues to emit the JSON manifest
separately.

Boundaries:

- ffmpeg is the only heavy dep (already in the light backend image).
- No watermark burn-in. ``watermark_status="pending"``.
- No C2PA signing. ``c2pa_status="pending"`` /
  ``disclosure_status="pending"``.
- No external upload. Output lives under
  ``ARTIFACTS_LOCAL_ROOT/final_export/<job_id>/``.

Categorised error codes — every failure returns HTTP 200 with a
structured ``status`` so the frontend can pattern-match (mirrors the
Phase 6A / 7B / 7D shape):

- ``job_not_found`` — 404 (only hard failure that surfaces as non-200).
- ``video_artifact_missing`` — no video artifact found for this job.
- ``video_artifact_not_found`` — explicit ``video_artifact_id`` doesn't exist.
- ``wrong_video_artifact_type`` — artifact exists but isn't a video.
- ``video_artifact_no_local_path`` — DB row has no on-disk file.
- ``source_outside_allowed_roots`` — defence against rogue DB rows.
- ``ffmpeg_missing`` / ``ffprobe_missing`` — image hygiene problem.
- ``export_failed`` — ffmpeg returned non-zero or timed out; partial
  cleanup ran.
- ``export_invalid`` — ffmpeg returned 0 but output is empty / has
  no video stream.
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
from app.services import artifact_service
from app.services.final_export import finalize_video

router = APIRouter(prefix="/api/v1/export", tags=["export"])


FinalExportStatus = Literal[
    "completed",
    "failed",
    "not_configured",
    "missing_inputs",
]


_FINAL_EXPORT_ERROR_CODES = (
    "video_artifact_missing",
    "video_artifact_not_found",
    "wrong_video_artifact_type",
    "video_artifact_no_local_path",
    "source_outside_allowed_roots",
    "ffmpeg_missing",
    "ffprobe_missing",
    "export_failed",
    "export_invalid",
)


class FinalizeExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: uuid.UUID
    video_artifact_id: uuid.UUID | None = None
    audio_artifact_id: uuid.UUID | None = None  # optional mux source
    watermark_required: bool = Field(default=True)
    c2pa_required: bool = Field(default=True)


class FinalizeExportResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: FinalExportStatus
    job_id: uuid.UUID
    final_export_artifact_id: uuid.UUID | None = None
    output_uri: str | None = None
    size_bytes: int | None = None
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    checksum_sha256: str | None = None
    error_code: str | None = None
    message: str = ""
    metadata: dict = Field(default_factory=dict)


def _allowed_artifact_roots() -> list[Path]:
    """Mirror the artifacts.py allow-list so the export endpoint only
    operates on files within trusted roots."""
    roots: list[Path] = []
    for env_name, default in (
        ("UPLOAD_AUDIO_ROOT", settings.upload_audio_root),
        ("UPLOAD_IMAGE_ROOT", settings.upload_image_root),
        ("UPLOAD_TEXT_ROOT", settings.upload_text_root),
        ("ARTIFACTS_LOCAL_ROOT", settings.artifacts_local_root),
    ):
        raw = os.environ.get(env_name, default)
        if raw:
            roots.append(Path(raw).resolve(strict=False))
    return roots


def _path_is_under_allowed_root(p: Path) -> bool:
    for root in _allowed_artifact_roots():
        try:
            p.relative_to(root)
            return True
        except ValueError:
            continue
    return False


async def _resolve_video_artifact(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    explicit_id: uuid.UUID | None,
) -> tuple[Artifact | None, str | None]:
    """Return (artifact, None) on success, or (None, error_code) when
    we can't pick a video artifact for the job."""
    if explicit_id is not None:
        row = await session.execute(select(Artifact).where(Artifact.id == explicit_id))
        art = row.scalar_one_or_none()
        if art is None:
            return None, "video_artifact_not_found"
        if art.artifact_type != ArtifactType.video.value:
            return None, "wrong_video_artifact_type"
        return art, None

    # No explicit id — pick the most recent video artifact for this job.
    row = await session.execute(
        select(Artifact)
        .where(
            Artifact.job_id == job_id,
            Artifact.artifact_type == ArtifactType.video.value,
        )
        .order_by(desc(Artifact.created_at))
        .limit(1)
    )
    art = row.scalar_one_or_none()
    if art is None:
        return None, "video_artifact_missing"
    return art, None


@router.post("/finalize", response_model=FinalizeExportResult)
async def export_finalize(
    payload: FinalizeExportRequest,
    session: AsyncSession = Depends(get_db_session),
) -> FinalizeExportResult:
    # 1. Job exists.
    job_row = await session.execute(select(Job).where(Job.id == payload.job_id))
    if job_row.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="job not found")

    # 2. Locate source video artifact.
    video_art, err = await _resolve_video_artifact(
        session, job_id=payload.job_id, explicit_id=payload.video_artifact_id
    )
    if err is not None or video_art is None:
        return FinalizeExportResult(
            status="missing_inputs",
            job_id=payload.job_id,
            error_code=err,
            message=(
                "no source video artifact available for this job. "
                "Run /api/v1/video/generate first (Phase 7D) or pass an "
                "explicit video_artifact_id."
                if err == "video_artifact_missing"
                else f"video artifact rejected: {err}"
            ),
        )

    # 3. Validate the source path is on disk and under an allowed root.
    if not video_art.local_path:
        return FinalizeExportResult(
            status="missing_inputs",
            job_id=payload.job_id,
            error_code="video_artifact_no_local_path",
            message="source video artifact has no local_path",
        )
    if ".." in video_art.local_path.split(os.sep):
        return FinalizeExportResult(
            status="not_configured",
            job_id=payload.job_id,
            error_code="source_outside_allowed_roots",
            message="source video path looks unsafe",
        )
    try:
        src = Path(video_art.local_path).resolve(strict=True)
    except FileNotFoundError:
        return FinalizeExportResult(
            status="missing_inputs",
            job_id=payload.job_id,
            error_code="video_artifact_no_local_path",
            message="source video file is not on disk",
        )
    if not _path_is_under_allowed_root(src):
        return FinalizeExportResult(
            status="not_configured",
            job_id=payload.job_id,
            error_code="source_outside_allowed_roots",
            message="source video path is outside allowed artifact roots",
        )

    # 4. Optional audio mux source.
    audio_path: Path | None = None
    if payload.audio_artifact_id is not None:
        aud_row = await session.execute(
            select(Artifact).where(Artifact.id == payload.audio_artifact_id)
        )
        aud = aud_row.scalar_one_or_none()
        if aud is None or aud.artifact_type != ArtifactType.audio.value:
            return FinalizeExportResult(
                status="missing_inputs",
                job_id=payload.job_id,
                error_code="video_artifact_not_found",
                message="audio_artifact_id is unknown or wrong type",
            )
        if not aud.local_path:
            return FinalizeExportResult(
                status="missing_inputs",
                job_id=payload.job_id,
                error_code="video_artifact_no_local_path",
                message="audio mux source has no local_path",
            )
        try:
            audio_path = Path(aud.local_path).resolve(strict=True)
        except FileNotFoundError:
            return FinalizeExportResult(
                status="missing_inputs",
                job_id=payload.job_id,
                error_code="video_artifact_no_local_path",
                message="audio mux source not on disk",
            )
        if not _path_is_under_allowed_root(audio_path):
            return FinalizeExportResult(
                status="not_configured",
                job_id=payload.job_id,
                error_code="source_outside_allowed_roots",
                message="audio mux source outside allowed roots",
            )

    # 5. Choose output directory under the artifacts root.
    artifacts_root = Path(
        os.environ.get("ARTIFACTS_LOCAL_ROOT", settings.artifacts_local_root)
    )
    out_dir = artifacts_root / "final_export" / str(payload.job_id)

    # 6. Run ffmpeg.
    result = finalize_video(
        source_path=src,
        output_dir=out_dir,
        audio_path=audio_path,
    )

    if result.status != "completed":
        return FinalizeExportResult(
            status="failed" if result.error_code == "export_failed" else "not_configured",
            job_id=payload.job_id,
            error_code=result.error_code,
            message=result.message,
            metadata={
                "ffmpeg_result": result.to_dict(),
            },
        )

    # 7. Register the final_export artifact row.
    assert result.output_path is not None  # narrowed by status=="completed"
    output_path = Path(result.output_path)
    metadata_json = {
        "phase": "phase8b_final_export",
        "kind": "real_mp4",
        "source_video_artifact_id": str(video_art.id),
        "source_audio_artifact_id": (
            str(payload.audio_artifact_id)
            if payload.audio_artifact_id is not None
            else None
        ),
        "watermark_required": payload.watermark_required,
        "c2pa_required": payload.c2pa_required,
        # Phase 8B never burns watermark or signs C2PA. The status
        # fields advertise that real disclosure work is still pending.
        "watermark_status": "pending",
        "c2pa_status": "pending",
        "disclosure_status": "pending",
        "ffmpeg": {
            "container_format": result.container_format,
            "video_codec": result.video_codec,
            "audio_codec": result.audio_codec,
            "video_stream_present": result.video_stream_present,
            "audio_stream_present": result.audio_stream_present,
        },
    }
    artifact = await artifact_service.register_artifact(
        session,
        job_id=payload.job_id,
        artifact_type=ArtifactType.final_export.value,
        uri=output_path.as_uri(),
        local_path=str(output_path),
        mime_type="video/mp4",
        checksum_sha256=result.checksum_sha256,
        size_bytes=result.size_bytes,
        duration_seconds=result.duration_seconds,
        width=result.width,
        height=result.height,
        metadata_json=metadata_json,
    )

    return FinalizeExportResult(
        status="completed",
        job_id=payload.job_id,
        final_export_artifact_id=artifact.id,
        output_uri=output_path.as_uri(),
        size_bytes=result.size_bytes,
        duration_seconds=result.duration_seconds,
        width=result.width,
        height=result.height,
        checksum_sha256=result.checksum_sha256,
        message="final export MP4 written and registered (no watermark / no C2PA yet).",
        metadata={
            "ffmpeg": metadata_json["ffmpeg"],
            "disclosure_status": "pending",
            "watermark_status": "pending",
            "c2pa_status": "pending",
        },
    )


_ = _FINAL_EXPORT_ERROR_CODES  # exported for tests / docs
