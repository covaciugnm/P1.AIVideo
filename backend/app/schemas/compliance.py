"""Pydantic schemas for compliance decisions."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.compliance import ComplianceDecisionType


class ComplianceDecision(BaseModel):
    """A single compliance-gate decision. Used both as a domain object and
    as a wire format for orchestrator → backend status updates."""

    job_id: uuid.UUID
    gate: str
    decision: ComplianceDecisionType
    reasons: list[str] = []


class ComplianceEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    gate: str
    decision: ComplianceDecisionType
    reasons: list[str]
    created_at: datetime
