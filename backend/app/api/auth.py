"""/api/v1/auth/* — login, register, me, change-password, logout."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
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
from app.services import auth_service, user_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse)
async def register(req: RegisterRequest, session: AsyncSession = Depends(get_db_session)):
    """PUBLIC. Creates a pending/operator/inactive user. Never auto-logs-in,
    never returns a token or password hash."""
    try:
        await user_service.register_user(session, req)
    except user_service.UserRuleError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
    return RegisterResponse(
        status="pending",
        message=(
            "Registration submitted. Your account must be approved by the "
            "administrator before you can log in."
        ),
    )


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, session: AsyncSession = Depends(get_db_session)):
    """PUBLIC. Returns a JWT on success; status-specific 403 otherwise."""
    try:
        user = await user_service.authenticate(session, req.username, req.password)
    except user_service.UserRuleError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
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
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Any logged-in user (incl. protected super admin) changes OWN password
    by supplying the current password. No other user can reset it."""
    try:
        await user_service.change_password(session, user, req.current_password, req.new_password)
    except user_service.UserRuleError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
    return MessageResponse(message="Password changed.")


@router.post("/logout", response_model=MessageResponse)
async def logout(user: User = Depends(get_current_user)):
    """Stateless JWT — logout is client-side token discard (no server-side
    blacklist in this phase). Documented as a remaining risk."""
    return MessageResponse(message="Logged out (discard the token client-side).")
