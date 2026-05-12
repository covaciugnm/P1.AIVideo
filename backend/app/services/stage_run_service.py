"""StageRun service — DB writes for DAG stage tracking."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.enums import StageStatus

from app.models.stage_run import StageRun


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def create_pending(session: AsyncSession, *, job_id: uuid.UUID, stage: str) -> StageRun:
    run = StageRun(job_id=job_id, stage=stage, status=StageStatus.running, started_at=_utcnow())
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def mark_succeeded(
    session: AsyncSession,
    run_id: uuid.UUID,
    *,
    artifacts: dict | None = None,
    extra: dict | None = None,
) -> None:
    run = await session.get(StageRun, run_id)
    if run is None:
        return
    run.status = StageStatus.succeeded
    run.artifacts = artifacts or {}
    run.extra = extra or {}
    run.finished_at = _utcnow()
    await session.commit()


async def mark_failed(session: AsyncSession, run_id: uuid.UUID, *, error: str) -> None:
    run = await session.get(StageRun, run_id)
    if run is None:
        return
    run.status = StageStatus.failed
    run.error = error[:1000]
    run.finished_at = _utcnow()
    await session.commit()


async def mark_rejected(session: AsyncSession, run_id: uuid.UUID, *, reason: str) -> None:
    run = await session.get(StageRun, run_id)
    if run is None:
        return
    run.status = StageStatus.rejected
    run.error = reason[:1000]
    run.finished_at = _utcnow()
    await session.commit()


async def list_for_job(session: AsyncSession, job_id: uuid.UUID) -> list[StageRun]:
    result = await session.execute(
        select(StageRun).where(StageRun.job_id == job_id).order_by(StageRun.started_at)
    )
    return list(result.scalars().all())
