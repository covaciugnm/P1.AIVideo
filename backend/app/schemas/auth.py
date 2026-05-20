"""Auth + user-management schemas. password_hash is NEVER included."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["super_admin", "admin", "operator", "viewer"]
UserStatus = Literal["pending", "active", "suspended", "rejected", "deleted"]


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")  # ignore role/status/etc if sent
    username: str = Field(..., min_length=3, max_length=150)
    email: str = Field(..., min_length=3, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)
    password: str = Field(..., min_length=1, max_length=256)


class RegisterResponse(BaseModel):
    status: str = "pending"
    message: str


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(..., max_length=150)
    password: str = Field(..., max_length=256)


class UserPublic(BaseModel):
    """Safe user representation — no password_hash, ever."""
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    username: str
    email: str | None = None
    full_name: str | None = None
    role: Role
    user_status: UserStatus
    is_active: bool
    is_protected: bool
    created_at: datetime | None = None
    last_login_at: datetime | None = None
    approved_at: datetime | None = None
    suspended_at: datetime | None = None
    rejected_at: datetime | None = None
    deleted_at: datetime | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(..., max_length=256)
    new_password: str = Field(..., max_length=256)


class MessageResponse(BaseModel):
    message: str


class UserListResponse(BaseModel):
    items: list[UserPublic]
    total: int


class ApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["operator", "viewer", "admin"] = "operator"


class ReasonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(default=None, max_length=500)
