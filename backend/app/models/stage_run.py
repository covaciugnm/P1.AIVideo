"""StageRun model — one row per DAG stage execution.

Phase 2 records every no-op stage. The `noop` flag is True in Phase 2;
later phases set it to False as real implementations land.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from common.enums import StageStatus

from app.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class StageRun(Base):
    __tablename__ = "stage_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[StageStatus] = mapped_column(
        Enum(StageStatus, name="stage_status"), nullable=False, default=StageStatus.pending
    )
    noop: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    artifacts: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
