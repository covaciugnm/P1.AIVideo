"""/api/v1/auth/* — login, register, me, change-password, logout."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    UserPublic,
)
from app.services import auth_service, security_audit_service, user_service

# Map login-failure detail → audit event + (severity).
_LOGIN_BLOCK_EVENTS = {
    "pending": "LOGIN_BLOCKED_PENDING",
    "suspended": "LOGIN_BLOCKED_SUSPENDED",
    "rejected": "LOGIN_BLOCKED_REJECTED",
    "unavailable": "LOGIN_BLOCKED_DELETED",
}

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse)
async def register(req: RegisterRequest, request: Request, session: AsyncSession = Depends(get_db_session)):
    """PUBLIC. Creates a pending/operator/inactive user. Never auto-logs-in,
    never returns a token or password hash."""
    try:
        await user_service.register_user(session, req)
    except user_service.UserRuleError as exc:
        evt = "REGISTER_REJECTED_WEAK_PASSWORD" if exc.status == 422 else (
            "REGISTER_REJECTED_DUPLICATE_EMAIL" if "email" in exc.detail.lower()
            else "REGISTER_REJECTED_DUPLICATE_USERNAME")
        await security_audit_service.log_auth_event(
            session, event_type=evt, result="failed", severity="warning",
            request=request, actor_username=req.username,
            metadata={"reason": exc.detail})
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
    await security_audit_service.log_auth_event(
        session, event_type="REGISTER_CREATED_PENDING", result="success",
        request=request, actor_username=req.username)
    return RegisterResponse(
        status="pending",
        message=(
            "Registration submitted. Your account must be approved by the "
            "administrator before you can log in."
        ),
    )


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request, session: AsyncSession = Depends(get_db_session)):
    """PUBLIC. Returns a JWT on success; status-specific 403 otherwise."""
    try:
        user = await user_service.authenticate(session, req.username, req.password)
    except user_service.UserRuleError as exc:
        # Determine the precise blocked/failed reason WITHOUT revealing whether
        # the username exists (we only log the attempted username).
        low = exc.detail.lower()
        evt = next((e for k, e in _LOGIN_BLOCK_EVENTS.items() if k in low), "LOGIN_FAILED")
        await security_audit_service.log_auth_event(
            session, event_type=evt, result=("blocked" if evt != "LOGIN_FAILED" else "failed"),
            severity="warning", request=request, actor_username=req.username,
            metadata={"reason": exc.detail})
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
    await security_audit_service.log_auth_event(
        session, event_type="LOGIN_SUCCESS", result="success", request=request, actor=user,
        metadata={"role": user.role})
    token, expires_in = auth_service.create_access_token(user)
    return TokenResponse(
        access_token=token, token_type="bearer", expires_in=expires_in,
        user=user_service.to_public(user),
    )


@router.get("/me", response_model=UserPublic)
async def me(user: User = Depends(get_current_user)):
    return user_service.to_public(user)


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    req: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Any logged-in user (incl. protected super admin) changes OWN password
    by supplying the current password. No other user can reset it."""
    try:
        await user_service.change_password(session, user, req.current_password, req.new_password)
    except user_service.UserRuleError as exc:
        await security_audit_service.log_auth_event(
            session, event_type="PASSWORD_CHANGE_FAILED", result="failed",
            severity="warning", request=request, actor=user, reason=exc.detail)
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
    await security_audit_service.log_auth_event(
        session, event_type="PASSWORD_CHANGE_SUCCESS", result="success",
        request=request, actor=user)
    return MessageResponse(message="Password changed.")


@router.post("/logout", response_model=MessageResponse)
async def logout(user: User = Depends(get_current_user)):
    """Stateless JWT — logout is client-side token discard (no server-side
    blacklist in this phase). Documented as a remaining risk."""
    return MessageResponse(message="Logged out (discard the token client-side).")
