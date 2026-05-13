"""Artifact service — DB writes for the first-class ``artifacts`` table.

Phase 3D scope: register an artifact row from either explicit kwargs or
from an existing ``ArtifactRef``. Metadata-only — never reads or writes
binary audio bytes here.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.schemas import ArtifactRef

from app.models.artifact import Artifact


async def register_artifact(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    stage_run_id: uuid.UUID | None = None,
    artifact_type: str,
    uri: str,
    local_path: str | None = None,
    mime_type: str | None = None,
    checksum_sha256: str | None = None,
    size_bytes: int | None = None,
    duration_seconds: float | None = None,
    sample_rate: int | None = None,
    channels: int | None = None,
    metadata_json: dict | None = None,
) -> Artifact:
    artifact = Artifact(
        job_id=job_id,
        stage_run_id=stage_run_id,
        artifact_type=artifact_type,
        uri=uri,
        local_path=local_path,
        mime_type=mime_type,
        checksum_sha256=checksum_sha256,
        size_bytes=size_bytes,
        duration_seconds=duration_seconds,
        sample_rate=sample_rate,
        channels=channels,
        metadata_json=metadata_json or {},
    )
    session.add(artifact)
    await session.commit()
    await session.refresh(artifact)
    return artifact


async def register_artifact_ref(
    session: AsyncSession,
    *,
    ref: ArtifactRef,
    job_id: uuid.UUID,
    stage_run_id: uuid.UUID | None = None,
    name: str | None = None,
) -> Artifact:
    """Convenience: persist an ``ArtifactRef`` (typically returned by a
    stage handler) into the artifacts table.

    ``ref.extra`` is merged into ``metadata_json`` with the optional
    ``name`` (e.g. ``"narration"``, ``"portrait"``) added in.
    """
    metadata: dict = dict(ref.extra)
    if name is not None:
        metadata["name"] = name
    mime = ref.extra.get("mime_type") if isinstance(ref.extra, dict) else None
    return await register_artifact(
        session,
        job_id=job_id,
        stage_run_id=stage_run_id,
        artifact_type=ref.artifact_type,
        uri=ref.uri,
        local_path=ref.local_path,
        mime_type=mime,
        checksum_sha256=ref.checksum_sha256,
        size_bytes=ref.size_bytes,
        duration_seconds=ref.duration_seconds,
        sample_rate=ref.sample_rate,
        channels=ref.channels,
        metadata_json=metadata,
    )


async def list_for_job(session: AsyncSession, job_id: uuid.UUID) -> list[Artifact]:
    result = await session.execute(
        select(Artifact).where(Artifact.job_id == job_id).order_by(Artifact.created_at)
    )
    return list(result.scalars().all())
