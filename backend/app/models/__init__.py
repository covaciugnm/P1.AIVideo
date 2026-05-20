"""Model package.

Importing this package eagerly loads every model module so that
`Base.metadata` is fully populated before any caller invokes
`Base.metadata.create_all()`.
"""
from app.models.api_secret import ApiSecret
from app.models.artifact import Artifact
from app.models.base import Base
from app.models.character import (
    CHARACTER_IMAGE_STATUSES,
    CHARACTER_STATUSES,
    Character,
    CharacterImage,
    CharacterVersion,
    CharacterVideo,
)
from app.models.compliance import ComplianceDecisionType, ComplianceEvent
from app.models.feature_provider import FeatureProvider
from app.models.job import Job, JobStatus
from app.models.operator_settings import OperatorSettings
from app.models.stage_run import StageRun
from app.models.security_audit import SecurityAuditEvent
from app.models.user import ROLES, USER_STATUSES, User

__all__ = [
    "ApiSecret",
    "Artifact",
    "Base",
    "ROLES",
    "USER_STATUSES",
    "User",
    "SecurityAuditEvent",
    "CHARACTER_IMAGE_STATUSES",
    "CHARACTER_STATUSES",
    "Character",
    "CharacterImage",
    "CharacterVersion",
    "CharacterVideo",
    "ComplianceDecisionType",
    "ComplianceEvent",
    "FeatureProvider",
    "Job",
    "JobStatus",
    "OperatorSettings",
    "StageRun",
]
