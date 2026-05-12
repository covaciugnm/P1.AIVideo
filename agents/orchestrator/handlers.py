"""Phase 1 orchestrator handler.

Bridges a parsed `job.created` event to:
  1. The policy_gate function in agents.compliance_officer.policy_gate
  2. The backend DB (status update + compliance event row)

The handler depends on `app.*` from the backend package. Phase 2 will pull
the shared DB layer into a small `aivideo-common` package so the
orchestrator no longer reaches into the backend.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Backend imports — Phase 1 accepts this coupling; Phase 2 refactors it.
from app.models.compliance import ComplianceDecisionType, ComplianceEvent
from app.models.job import JobStatus
from app.services import job_service

from agents.compliance_officer.policy_gate import (
    JobBriefView,
    PolicyGateDecision,
    policy_gate,
)

log = logging.getLogger(__name__)


def make_job_created_handler(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> Callable[[dict[str, Any]], Awaitable[None]]:
    """Return a handler closure bound to a SQLAlchemy session factory."""

    async def handle(payload: dict[str, Any]) -> None:
        if payload.get("event") != "job.created":
            log.debug("orchestrator: ignoring non-job.created event")
            return

        try:
            job_id = uuid.UUID(payload["job_id"])
        except (KeyError, ValueError):
            log.warning("orchestrator: payload missing/invalid job_id")
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
