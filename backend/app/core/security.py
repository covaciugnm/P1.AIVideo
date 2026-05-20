"""Auth dependencies + RBAC — security remediation.

Guards:
  get_current_user          — STRICT: valid token + user exists + active.
                              Used by /auth/me etc. Always enforces.
  require_active_user       — router guard; no-op when P1_AUTH_ENABLED=false.
  require_super_admin       — protected super admin only; no-op when disabled.
  require_operator_or_above — super_admin/admin/operator; no-op when disabled.

The disable bypass exists ONLY so the legacy test-suite (which predates auth)
can run with P1_AUTH_ENABLED=false. Production keeps auth enabled (the default),
so every guard enforces.
"""
from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_db_session
from app.models.user import User
from app.services import auth_service

_UNAUTH = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)
_FORBIDDEN = HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")


async def _resolve_user(request: Request, session: AsyncSession) -> User:
    auth = request.headers.get("Authorization") or ""
    if not auth.lower().startswith("bearer "):
        raise _UNAUTH
    token = auth.split(" ", 1)[1].strip()
    try:
        payload = auth_service.decode_access_token(token)
        user_id = uuid.UUID(payload.get("sub", ""))
    except (auth_service.TokenError, ValueError, TypeError):
        raise _UNAUTH
    user = await auth_service.get_user_by_id(session, user_id)
    if user is None or not user.is_active or user.user_status != "active":
        raise _UNAUTH
    return user


async def get_current_user(
    request: Request, session: AsyncSession = Depends(get_db_session)
) -> User:
    """STRICT — always requires a valid token (used by auth-specific routes)."""
    return await _resolve_user(request, session)


async def require_active_user(
    request: Request, session: AsyncSession = Depends(get_db_session)
) -> User | None:
    if not settings.p1_auth_enabled:
        return None
    return await _resolve_user(request, session)


async def require_super_admin(
    request: Request, session: AsyncSession = Depends(get_db_session)
) -> User | None:
    if not settings.p1_auth_enabled:
        return None
    user = await _resolve_user(request, session)
    if not auth_service.is_protected_super_admin(user):
        raise _FORBIDDEN
    return user


async def require_operator_or_above(
    request: Request, session: AsyncSession = Depends(get_db_session)
) -> User | None:
    if not settings.p1_auth_enabled:
        return None
    user = await _resolve_user(request, session)
    if user.role not in ("super_admin", "admin", "operator"):
        raise _FORBIDDEN
    return user
