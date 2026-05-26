"""User lifecycle service — registration, login checks, admin transitions.

All protected-super-admin invariants and allowed/forbidden state transitions
are enforced here (single source of truth). Raises UserRuleError → API maps
to the documented HTTP codes.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.auth import RegisterRequest, UserPublic
from app.services import auth_service


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UserRuleError(Exception):
    """Validation/permission rule violation. ``status`` is the HTTP code."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def to_public(user: User) -> UserPublic:
    return UserPublic(
        id=user.id, username=user.username, email=user.email,
        full_name=user.full_name, role=user.role,  # type: ignore[arg-type]
        user_status=user.user_status,  # type: ignore[arg-type]
        is_active=user.is_active, is_protected=user.is_protected,
        created_at=user.created_at, last_login_at=user.last_login_at,
        approved_at=user.approved_at, suspended_at=user.suspended_at,
        rejected_at=user.rejected_at, deleted_at=user.deleted_at,
    )


# ----- registration --------------------------------------------------------

async def register_user(session: AsyncSession, req: RegisterRequest) -> User:
    """Create a self-service account in the locked-down default state.

    Invariant: public registration ALWAYS yields role ``operator``,
    status ``pending`` and ``is_active=False`` — any privileged fields in the
    request are ignored (the schema drops them). The account cannot log in
    until a super-admin approves it. Raises :class:`UserRuleError` on weak
    password (422) or duplicate username/email (409).
    """
    err = auth_service.validate_password_policy(req.password)
    if err:
        raise UserRuleError(422, err)
    if await auth_service.get_user_by_username(session, req.username):
        raise UserRuleError(409, "Username already taken.")
    if req.email and await auth_service.get_user_by_email(session, req.email):
        raise UserRuleError(409, "Email already registered.")
    # Public registration ALWAYS pending/operator/inactive — submitted
    # role/status/is_active/is_protected fields are ignored by the schema.
    user = User(
        id=uuid.uuid4(),
        username=req.username,
        email=req.email,
        full_name=req.full_name,
        password_hash=auth_service.hash_password(req.password),
        role="operator",
        user_status="pending",
        is_active=False,
        is_protected=False,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


# ----- login ----------------------------------------------------------------

_STATUS_LOGIN_MSG = {
    "pending": (403, "Account pending administrator approval."),
    "rejected": (403, "Account registration was rejected."),
    "suspended": (403, "Account suspended. Contact administrator."),
    "deleted": (403, "Account unavailable."),
}


async def authenticate(session: AsyncSession, username: str, password: str) -> User:
    """Return the user on success, else raise UserRuleError. Generic 401 on
    bad credentials (never reveal whether the username exists)."""
    user = await auth_service.get_user_by_username(session, username)
    if user is None or not auth_service.verify_password(password, user.password_hash):
        raise UserRuleError(401, "Invalid username or password.")
    if user.user_status != "active" or not user.is_active:
        code, msg = _STATUS_LOGIN_MSG.get(user.user_status, (403, "Account unavailable."))
        raise UserRuleError(code, msg)
    user.last_login_at = _utcnow()
    await session.commit()
    return user


async def change_password(
    session: AsyncSession, user: User, current_password: str, new_password: str
) -> None:
    if not auth_service.verify_password(current_password, user.password_hash):
        raise UserRuleError(400, "Current password is incorrect.")
    err = auth_service.validate_password_policy(new_password)
    if err:
        raise UserRuleError(422, err)
    user.password_hash = auth_service.hash_password(new_password)
    user.password_changed_at = _utcnow()
    await session.commit()


# ----- admin transitions ----------------------------------------------------

def _guard_not_protected(user: User, action: str) -> None:
    if auth_service.is_protected_super_admin(user) or user.is_protected:
        raise UserRuleError(403, f"Protected super admin cannot be {action}.")


async def list_users(
    session: AsyncSession, *, status: str | None = None, include_deleted: bool = False
) -> tuple[list[User], int]:
    """Return ``(users, count)`` newest-first.

    ``status`` filters to one ``user_status``. With no filter, soft-deleted
    users are hidden unless ``include_deleted`` is set.
    """
    stmt = select(User)
    if status:
        stmt = stmt.where(User.user_status == status)
    elif not include_deleted:
        stmt = stmt.where(User.user_status != "deleted")
    stmt = stmt.order_by(User.created_at.desc())
    rows = list((await session.execute(stmt)).scalars().all())
    return rows, len(rows)


async def approve(session: AsyncSession, target: User, role: str, by: User) -> User:
    """Activate a pending user with the granted ``role`` (operator/viewer/admin).

    Transition ``pending → active`` only. Records who approved and when.
    Raises :class:`UserRuleError` on a protected account (403), a non-pending
    target (409) or an invalid role (422).
    """
    _guard_not_protected(target, "approved")
    if target.user_status != "pending":
        raise UserRuleError(409, f"Only pending users can be approved (is {target.user_status}).")
    if role not in ("operator", "viewer", "admin"):
        raise UserRuleError(422, "Invalid approval role.")
    target.user_status = "active"
    target.is_active = True
    target.role = role
    target.approved_at = _utcnow()
    target.approved_by_user_id = by.id
    target.updated_at = _utcnow()
    await session.commit()
    await session.refresh(target)
    return target


async def reject(session: AsyncSession, target: User, reason: str | None, by: User) -> User:
    """Reject a pending registration (``pending → rejected``, stays inactive).

    Raises :class:`UserRuleError` on a protected account (403) or a
    non-pending target (409).
    """
    _guard_not_protected(target, "rejected")
    if target.user_status != "pending":
        raise UserRuleError(409, "Only pending users can be rejected.")
    target.user_status = "rejected"
    target.is_active = False
    target.rejected_at = _utcnow()
    target.rejected_by_user_id = by.id
    target.rejection_reason = reason
    target.updated_at = _utcnow()
    await session.commit()
    await session.refresh(target)
    return target


async def suspend(session: AsyncSession, target: User, reason: str | None, by: User) -> User:
    """Suspend an active user (``active → suspended``, blocks login).

    Reversible via :func:`reactivate`. Raises :class:`UserRuleError` on a
    protected account (403) or a non-active target (409).
    """
    _guard_not_protected(target, "suspended")
    if target.user_status != "active":
        raise UserRuleError(409, "Only active users can be suspended.")
    target.user_status = "suspended"
    target.is_active = False
    target.suspended_at = _utcnow()
    target.suspended_by_user_id = by.id
    target.suspension_reason = reason
    target.updated_at = _utcnow()
    await session.commit()
    await session.refresh(target)
    return target


async def reactivate(session: AsyncSession, target: User, by: User) -> User:
    """Restore a suspended user (``suspended → active``, login re-enabled).

    Raises :class:`UserRuleError` on a protected account (403) or a
    non-suspended target (409).
    """
    _guard_not_protected(target, "reactivated")
    if target.user_status != "suspended":
        raise UserRuleError(409, "Only suspended users can be reactivated.")
    target.user_status = "active"
    target.is_active = True
    target.updated_at = _utcnow()
    await session.commit()
    await session.refresh(target)
    return target


async def soft_delete(
    session: AsyncSession, target: User, reason: str | None, by: User
) -> User:
    """Soft-delete a user (``→ deleted``, inactive; row is retained for audit).

    Self-deletion is forbidden (403). Raises :class:`UserRuleError` on a
    protected account (403) or an already-deleted target (409).
    """
    _guard_not_protected(target, "deleted")
    if target.id == by.id:
        raise UserRuleError(403, "Users cannot delete themselves.")
    if target.user_status == "deleted":
        raise UserRuleError(409, "User is already deleted.")
    target.user_status = "deleted"
    target.is_active = False
    target.deleted_at = _utcnow()
    target.deleted_by_user_id = by.id
    target.deletion_reason = reason
    target.updated_at = _utcnow()
    await session.commit()
    await session.refresh(target)
    return target
