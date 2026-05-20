"""User model — authentication / RBAC / registration (security remediation).

Roles: super_admin | admin | operator | viewer.
Statuses: pending | active | suspended | rejected | deleted.

Invariants enforced in the service layer (user_service):
  - active        => is_active = true
  - non-active    => is_active = false
  - protected super admin is always (active, is_active=true, super_admin,
    is_protected=true) and cannot be deleted/suspended/rejected/demoted/renamed.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

ROLES = ("super_admin", "admin", "operator", "viewer")
USER_STATUSES = ("pending", "active", "suspended", "rejected", "deleted")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(150), nullable=False, unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # password_hash is NEVER exposed in any schema/API response.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[str] = mapped_column(
        String(32), nullable=False, default="operator", server_default="operator", index=True
    )
    user_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending", index=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false", index=True
    )
    is_protected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false", index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False, server_default=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    suspended_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    suspension_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    deletion_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
