"""/api/v1/users/* — user management. Protected-super-admin only (this phase).

Router-level guard: every route depends on require_super_admin.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.core.security import require_super_admin
from app.models.user import User
from app.schemas.auth import (
    ApproveRequest,
    ReasonRequest,
    UserListResponse,
    UserPublic,
)
from app.services import auth_service, security_audit_service, user_service

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/v1/users",
    tags=["users"],
    dependencies=[Depends(require_super_admin)],
)


async def _load(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await auth_service.get_user_by_id(session, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return user


@router.get("", response_model=UserListResponse)
async def list_users(
    status: str | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session),
):
    rows, total = await user_service.list_users(
        session, status=status, include_deleted=include_deleted
    )
    return UserListResponse(items=[user_service.to_public(u) for u in rows], total=total)


@router.get("/pending", response_model=UserListResponse)
async def list_pending(session: AsyncSession = Depends(get_db_session)):
    rows, total = await user_service.list_users(session, status="pending")
    return UserListResponse(items=[user_service.to_public(u) for u in rows], total=total)


@router.get("/{user_id}", response_model=UserPublic)
async def get_user(user_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)):
    return user_service.to_public(await _load(session, user_id))


async def _run_transition(
    *, session, request, actor, target, ok_event, fn, reason=None,
):
    """Run a user transition with audit on success / denial. Protected
    super-admin blocks are logged as PROTECTED_SUPER_ADMIN_MODIFICATION_BLOCKED."""
    old_status, old_role = target.user_status, target.role
    try:
        updated = await fn()
    except user_service.UserRuleError as exc:
        is_protected = (
            auth_service.is_protected_super_admin(target) or target.is_protected
        )
        evt = "PROTECTED_SUPER_ADMIN_MODIFICATION_BLOCKED" if (exc.status == 403 and is_protected) else f"{ok_event}_DENIED"
        await security_audit_service.log_user_admin_event(
            session, event_type=evt, result=("blocked" if is_protected else "denied"),
            severity="warning", request=request, actor=actor, target=target,
            reason=exc.detail)
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
    await security_audit_service.log_user_admin_event(
        session, event_type=ok_event, result="success", request=request,
        actor=actor, target=updated, reason=reason,
        metadata={"old_status": old_status, "new_status": updated.user_status,
                  "old_role": old_role, "new_role": updated.role})
    return updated


@router.post("/{user_id}/approve", response_model=UserPublic)
async def approve_user(
    user_id: uuid.UUID, req: ApproveRequest, request: Request,
    actor: User = Depends(require_super_admin),
    session: AsyncSession = Depends(get_db_session),
):
    target = await _load(session, user_id)
    target = await _run_transition(
        session=session, request=request, actor=actor, target=target,
        ok_event="USER_APPROVED", fn=lambda: user_service.approve(session, target, req.role, actor))
    return user_service.to_public(target)


@router.post("/{user_id}/reject", response_model=UserPublic)
async def reject_user(
    user_id: uuid.UUID, request: Request, req: ReasonRequest | None = None,
    actor: User = Depends(require_super_admin),
    session: AsyncSession = Depends(get_db_session),
):
    target = await _load(session, user_id)
    reason = req.reason if req else None
    target = await _run_transition(
        session=session, request=request, actor=actor, target=target, reason=reason,
        ok_event="USER_REJECTED", fn=lambda: user_service.reject(session, target, reason, actor))
    return user_service.to_public(target)


@router.post("/{user_id}/suspend", response_model=UserPublic)
async def suspend_user(
    user_id: uuid.UUID, request: Request, req: ReasonRequest | None = None,
    actor: User = Depends(require_super_admin),
    session: AsyncSession = Depends(get_db_session),
):
    target = await _load(session, user_id)
    reason = req.reason if req else None
    target = await _run_transition(
        session=session, request=request, actor=actor, target=target, reason=reason,
        ok_event="USER_SUSPENDED", fn=lambda: user_service.suspend(session, target, reason, actor))
    return user_service.to_public(target)


@router.post("/{user_id}/reactivate", response_model=UserPublic)
async def reactivate_user(
    user_id: uuid.UUID, request: Request,
    actor: User = Depends(require_super_admin),
    session: AsyncSession = Depends(get_db_session),
):
    target = await _load(session, user_id)
    target = await _run_transition(
        session=session, request=request, actor=actor, target=target,
        ok_event="USER_REACTIVATED", fn=lambda: user_service.reactivate(session, target, actor))
    return user_service.to_public(target)


@router.delete("/{user_id}", response_model=UserPublic)
async def delete_user(
    user_id: uuid.UUID, request: Request,
    reason: str | None = Query(default=None),
    actor: User = Depends(require_super_admin),
    session: AsyncSession = Depends(get_db_session),
):
    target = await _load(session, user_id)
    target = await _run_transition(
        session=session, request=request, actor=actor, target=target, reason=reason,
        ok_event="USER_SOFT_DELETED", fn=lambda: user_service.soft_delete(session, target, reason, actor))
    return user_service.to_public(target)
