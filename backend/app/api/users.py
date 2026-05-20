"""/api/v1/users/* — user management. Protected-super-admin only (this phase).

Router-level guard: every route depends on require_super_admin.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
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
from app.services import auth_service, user_service

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


def _err(exc: user_service.UserRuleError):
    raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


@router.post("/{user_id}/approve", response_model=UserPublic)
async def approve_user(
    user_id: uuid.UUID, req: ApproveRequest,
    actor: User = Depends(require_super_admin),
    session: AsyncSession = Depends(get_db_session),
):
    target = await _load(session, user_id)
    try:
        target = await user_service.approve(session, target, req.role, actor)
    except user_service.UserRuleError as exc:
        _err(exc)
    return user_service.to_public(target)


@router.post("/{user_id}/reject", response_model=UserPublic)
async def reject_user(
    user_id: uuid.UUID, req: ReasonRequest | None = None,
    actor: User = Depends(require_super_admin),
    session: AsyncSession = Depends(get_db_session),
):
    target = await _load(session, user_id)
    try:
        target = await user_service.reject(session, target, (req.reason if req else None), actor)
    except user_service.UserRuleError as exc:
        _err(exc)
    return user_service.to_public(target)


@router.post("/{user_id}/suspend", response_model=UserPublic)
async def suspend_user(
    user_id: uuid.UUID, req: ReasonRequest | None = None,
    actor: User = Depends(require_super_admin),
    session: AsyncSession = Depends(get_db_session),
):
    target = await _load(session, user_id)
    try:
        target = await user_service.suspend(session, target, (req.reason if req else None), actor)
    except user_service.UserRuleError as exc:
        _err(exc)
    return user_service.to_public(target)


@router.post("/{user_id}/reactivate", response_model=UserPublic)
async def reactivate_user(
    user_id: uuid.UUID,
    actor: User = Depends(require_super_admin),
    session: AsyncSession = Depends(get_db_session),
):
    target = await _load(session, user_id)
    try:
        target = await user_service.reactivate(session, target, actor)
    except user_service.UserRuleError as exc:
        _err(exc)
    return user_service.to_public(target)


@router.delete("/{user_id}", response_model=UserPublic)
async def delete_user(
    user_id: uuid.UUID,
    reason: str | None = Query(default=None),
    actor: User = Depends(require_super_admin),
    session: AsyncSession = Depends(get_db_session),
):
    target = await _load(session, user_id)
    try:
        target = await user_service.soft_delete(session, target, reason, actor)
    except user_service.UserRuleError as exc:
        _err(exc)
    return user_service.to_public(target)
