"""Compliance event rows — audit-grade, append-only."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

# Re-export from common; same identity as common.enums.ComplianceDecisionType.
from common.enums import ComplianceDecisionType  # noqa: F401

from app.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ComplianceEvent(Base):
    """One row per compliance-gate evaluation.

    Phase 2 writes rows for: policy_gate, identity_guard, pre_lipsync_auth,
    export_disclosure_validation.
    """

    __tablename__ = "compliance_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    gate: Mapped[str] = mapped_column(String(50), nullable=False)
    decision: Mapped[ComplianceDecisionType] = mapped_column(
        Enum(ComplianceDecisionType, name="compliance_decision"), nullable=False
    )
    reasons: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
