"""Authentication service — password hashing, policy, JWT, bootstrap.

Security notes:
  - Passwords are hashed with Argon2id (argon2-cffi). Plaintext is never
    stored or logged.
  - JWT (HS256 by default) signed with P1_JWT_SECRET.
  - Generic errors on auth failure; we never reveal whether a username exists.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)

_ph = PasswordHasher()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Password hashing + policy
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


_SPECIAL_RE = re.compile(r"[^A-Za-z0-9]")


def validate_password_policy(password: str) -> str | None:
    """Return an error message if the password fails policy, else None.
    Never logs the password."""
    if not password or len(password) < 10:
        return "Password must be at least 10 characters."
    if not re.search(r"[A-Z]", password):
        return "Password must contain an uppercase letter."
    if not re.search(r"[a-z]", password):
        return "Password must contain a lowercase letter."
    if not re.search(r"\d", password):
        return "Password must contain a digit."
    if not _SPECIAL_RE.search(password):
        return "Password must contain a special character."
    return None


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

def create_access_token(user: User) -> tuple[str, int]:
    """Return (token, expires_in_seconds)."""
    expire_minutes = settings.p1_access_token_expire_minutes
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=expire_minutes)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    token = jwt.encode(payload, settings.p1_jwt_secret, algorithm=settings.p1_jwt_algorithm)
    return token, expire_minutes * 60


class TokenError(Exception):
    """Raised for any invalid/expired token; the API maps it to 401."""


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token, settings.p1_jwt_secret, algorithms=[settings.p1_jwt_algorithm]
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token expired") from exc
    except jwt.PyJWTError as exc:
        raise TokenError("invalid token") from exc
    if payload.get("type") != "access":
        raise TokenError("wrong token type")
    return payload


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    res = await session.execute(select(User).where(User.username == username))
    return res.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    res = await session.execute(select(User).where(User.id == user_id))
    return res.scalar_one_or_none()


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    res = await session.execute(select(User).where(User.email == email))
    return res.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Bootstrap protected super admin
# ---------------------------------------------------------------------------

async def bootstrap_super_admin(session: AsyncSession) -> None:
    """Create or repair the protected super admin. Idempotent. Never logs
    the password. Called at startup when auth is enabled."""
    username = settings.p1_super_admin_username
    existing = await get_user_by_username(session, username)
    if existing is None:
        password = settings.p1_super_admin_password
        if not password:
            raise RuntimeError(
                "Protected super admin does not exist and P1_SUPER_ADMIN_PASSWORD "
                "is not set. Set it in .env to bootstrap. (value not shown)"
            )
        err = validate_password_policy(password)
        if err:
            raise RuntimeError(f"P1_SUPER_ADMIN_PASSWORD rejected by policy: {err}")
        user = User(
            id=uuid.uuid4(),
            username=username,
            email=settings.p1_super_admin_email or None,
            full_name="P1.AIVideo Super Admin",
            password_hash=hash_password(password),
            role="super_admin",
            user_status="active",
            is_active=True,
            is_protected=True,
            password_changed_at=_utcnow(),
        )
        session.add(user)
        await session.commit()
        logger.info("Protected super admin created")
        return
    # Repair invariants WITHOUT touching the password.
    changed = False
    if existing.role != "super_admin":
        existing.role = "super_admin"; changed = True
    if existing.user_status != "active":
        existing.user_status = "active"; changed = True
    if not existing.is_active:
        existing.is_active = True; changed = True
    if not existing.is_protected:
        existing.is_protected = True; changed = True
    if not existing.email and settings.p1_super_admin_email:
        existing.email = settings.p1_super_admin_email; changed = True
    if changed:
        await session.commit()
    logger.info("Protected super admin exists")


def is_protected_super_admin(user: User) -> bool:
    return bool(
        user.is_protected
        and user.role == "super_admin"
        and user.username == settings.p1_super_admin_username
    )
