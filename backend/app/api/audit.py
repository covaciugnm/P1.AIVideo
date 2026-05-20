"""/api/v1/audit/* — read the persistent security audit trail.

Protected super admin only. Returns already-redacted events (the service
never persisted secrets/passwords/tokens in the first place).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.core.security import require_super_admin
from app.models.security_audit import SecurityAuditEvent

router = APIRouter(
    prefix="/api/v1/audit",
    tags=["audit"],
    dependencies=[Depends(require_super_admin)],
)


class SecurityAuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    event_type: str
    severity: str
    result: str
    actor_user_id: uuid.UUID | None = None
    actor_username: str | None = None
    actor_role: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    endpoint: str | None = None
    method: str | None = None
    request_id: str | None = None
    ip_address: str | None = None
    reason: str | None = None
    metadata_json: dict | None = None
    created_at: datetime


class SecurityAuditListResponse(BaseModel):
    items: list[SecurityAuditEventOut]
    total: int


@router.get("/security-events", response_model=SecurityAuditListResponse)
async def list_security_events(
    event_type: str | None = Query(default=None),
    actor_user_id: uuid.UUID | None = Query(default=None),
    target_type: str | None = Query(default=None),
    target_id: str | None = Query(default=None),
    result: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = select(SecurityAuditEvent)
    M = SecurityAuditEvent
    if event_type:
        stmt = stmt.where(M.event_type == event_type)
    if actor_user_id:
        stmt = stmt.where(M.actor_user_id == actor_user_id)
    if target_type:
        stmt = stmt.where(M.target_type == target_type)
    if target_id:
        stmt = stmt.where(M.target_id == target_id)
    if result:
        stmt = stmt.where(M.result == result)
    if severity:
        stmt = stmt.where(M.severity == severity)
    if date_from:
        stmt = stmt.where(M.created_at >= date_from)
    if date_to:
        stmt = stmt.where(M.created_at <= date_to)
    stmt = stmt.order_by(M.created_at.desc()).offset(offset).limit(limit)
    rows = list((await session.execute(stmt)).scalars().all())
    return SecurityAuditListResponse(
        items=[SecurityAuditEventOut.model_validate(r) for r in rows], total=len(rows)
    )
