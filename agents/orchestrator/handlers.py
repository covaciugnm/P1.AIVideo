"""Orchestrator handlers.

Two factories live here. They share the same `Handler` signature so either
can be plugged into `Orchestrator(handler=...)`.

- `make_policy_gate_handler` — Phase 1 narrow handler. Runs only the
  intake policy gate against a job and stops at `JobStatus.accepted`
  (or `rejected`). Preserved for the Phase 1 test and for any deployment
  that intentionally wants to validate the brief without continuing.

- `make_job_created_handler` — **Phase 2 default**. Wraps a `DagRunner` and
  executes the full no-op DAG (policy_gate → scriptwriter → voice → face →
  identity_guard → pre_lipsync_auth → lipsync → editor → qc →
  export_disclosure_validation → publisher). A valid job reaches
  `JobStatus.published`. This is the handler wired into the production
  Redis consumer path.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Backend imports — Phase 2 coupling; tracked for Phase 3 refactor.
from app.models.compliance import ComplianceDecisionType, ComplianceEvent
from app.models.job import JobStatus
from app.services import job_service

from agents.compliance_officer.policy_gate import (
    JobBriefView,
    PolicyGateDecision,
    policy_gate,
)
from agents.orchestrator.dag import DagRunner, DagRunnerConfig

log = logging.getLogger(__name__)

Handler = Callable[[dict[str, Any]], Awaitable[None]]


def _parse_job_id(payload: dict[str, Any]) -> uuid.UUID | None:
    if payload.get("event") != "job.created":
        log.debug("orchestrator: ignoring non-job.created event")
        return None
    try:
        return uuid.UUID(payload["job_id"])
    except (KeyError, ValueError):
        log.warning("orchestrator: payload missing/invalid job_id")
        return None


def make_policy_gate_handler(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> Handler:
    """Phase 1 narrow handler — runs only policy_gate.

    Preserved for the Phase 1 integration test. Production code should
    wire `make_job_created_handler` instead.
    """

    async def handle(payload: dict[str, Any]) -> None:
        job_id = _parse_job_id(payload)
        if job_id is None:
            return

        async with sessionmaker() as session:
            job = await job_service.get_job(session, job_id)
            if job is None:
                log.warning("orchestrator: job %s not found in DB", job_id)
                return

            view = JobBriefView(
                job_id=str(job.id),
                brief=job.brief,
                synthetic_person_confirmed=job.synthetic_person_confirmed,
                consent_confirmed=job.consent_confirmed,
                watermark_required=job.watermark_required,
                c2pa_required=job.c2pa_required,
            )
            decision: PolicyGateDecision = policy_gate(view)

            event = ComplianceEvent(
                job_id=job.id,
                gate="policy_gate",
                decision=(
                    ComplianceDecisionType.accept
                    if decision.accepted
                    else ComplianceDecisionType.reject
                ),
                reasons=decision.reasons,
                # Phase 3C/E: record declared voice + face sources for audit.
                extra={
                    "voice_source": job.voice_mode,
                    "face_source": job.face_mode or "stub",
                },
            )
            session.add(event)

            if decision.accepted:
                job.status = JobStatus.accepted
                job.rejection_reason = None
            else:
                job.status = JobStatus.rejected
                job.rejection_reason = ("; ".join(decision.reasons))[:1000]

            await session.commit()

    return handle


def make_job_created_handler(
    sessionmaker: async_sessionmaker[AsyncSession],
    dag_config: DagRunnerConfig,
) -> Handler:
    """Phase 2 production handler — runs the full no-op DAG via DagRunner.

    A `DagRunner` is constructed once (loading the pipeline YAML and stage
    handler registry) and reused for every event. Per-job state lives on
    the `DagState` object created inside `runner.run(job_id)`.
    """
    runner = DagRunner(sessionmaker, dag_config)

    async def handle(payload: dict[str, Any]) -> None:
        job_id = _parse_job_id(payload)
        if job_id is None:
            return
        # DagRunner already updates job + stage_runs + compliance_events.
        # It catches StageRejection / StageError internally and updates
        # status to rejected / failed; we don't need to wrap further.
        await runner.run(job_id)

    return handle
