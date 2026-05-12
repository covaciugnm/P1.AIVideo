"""Model package.

Importing this package eagerly loads every model module so that
`Base.metadata` is fully populated before any caller invokes
`Base.metadata.create_all()`. Without this, `create_all` runs against
whichever subset of models happens to have been imported so far — which is
how the Phase 1 `compliance_events` table was silently being skipped.
"""
from app.models.base import Base
from app.models.compliance import ComplianceDecisionType, ComplianceEvent
from app.models.job import Job, JobStatus

__all__ = [
    "Base",
    "ComplianceDecisionType",
    "ComplianceEvent",
    "Job",
    "JobStatus",
]
