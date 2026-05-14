"""Artifact model — first-class artifacts table (Phase 3D).

Distinct from ``stage_runs.artifacts`` (a denormalized JSON snapshot of
what each stage produced): this table stores one row per registered
artifact, queryable independently of the stage that produced it. Future
phases will index on ``checksum_sha256`` to dedupe across jobs and on
``artifact_type`` for analytics.

The DAG runner registers an artifact row for every ``ArtifactRef`` in a
stage's output that has a ``checksum_sha256`` set — i.e. real validated
files, not stub URIs.

Field naming uses ``metadata_json`` (not ``metadata``) because
``metadata`` is reserved on SQLAlchemy ``DeclarativeBase`` and would
shadow the class-level mapper metadata.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Nullable so Phase 4A-2 upload endpoints can register an "orphan"
    # artifact before a job exists. A subsequent
    # ``POST /api/v1/jobs/from-inputs`` references this artifact by id; the
    # original row stays as the intake record (``job_id`` stays NULL — the
    # job's own ``audio_ref`` / ``image_ref`` captures the linkage instead).
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    stage_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("stage_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    artifact_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    uri: Mapped[str] = mapped_column(String(2000), nullable=False)
    local_path: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Phase 3E: image dimensions (None for non-image artifacts).
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
