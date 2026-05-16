"""Model package.

Importing this package eagerly loads every model module so that
`Base.metadata` is fully populated before any caller invokes
`Base.metadata.create_all()`.
"""
from app.models.artifact import Artifact
from app.models.base import Base
from app.models.compliance import ComplianceDecisionType, ComplianceEvent
from app.models.job import Job, JobStatus
from app.models.operator_settings import OperatorSettings
from app.models.stage_run import StageRun

__all__ = [
    "Artifact",
    "Base",
    "ComplianceDecisionType",
    "ComplianceEvent",
    "Job",
    "JobStatus",
    "OperatorSettings",
    "StageRun",
]
