"""Security audit service — persistent + structured security observability.

Every helper: (1) emits a structured ``security.audit`` log record, (2) best
-effort persists a SecurityAuditEvent row, and (3) NEVER raises into the
request path (audit failures are logged, not propagated). Sensitive values
are redacted before logging/persisting.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.security_audit import SecurityAuditEvent

logger = logging.getLogger("security.audit")

# Keys whose values must never be stored/logged.
_REDACT_KEYS = {
    "password", "current_password", "new_password", "confirm", "confirm_password",
    "password_hash", "token", "access_token", "authorization", "secret",
    "secret_value", "api_key", "apikey", "jwt", "bearer",
}
_REDACTED = "***REDACTED***"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def redact(meta: dict | None) -> dict | None:
    if not meta:
        return meta
    out: dict[str, Any] = {}
    for k, v in meta.items():
        if any(s in k.lower() for s in _REDACT_KEYS):
            out[k] = _REDACTED
        elif isinstance(v, dict):
            out[k] = redact(v)
        else:
            out[k] = v
    return out


def _client_ip(request) -> str | None:
    if request is None:
        return None
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return getattr(getattr(request, "client", None), "host", None)


async def record(
    session: AsyncSession | None,
    *,
    event_type: str,
    result: str,
    severity: str = "info",
    request=None,
    actor=None,                 # User | None
    actor_username: str | None = None,
    actor_role: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    reason: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Record one security audit event. Best-effort persistence; never raises."""
    a_id = getattr(actor, "id", None)
    a_user = actor_username or getattr(actor, "username", None)
    a_role = actor_role or getattr(actor, "role", None)
    endpoint = method = request_id = ip = ua = None
    if request is not None:
        endpoint = str(getattr(request.url, "path", ""))[:255] or None
        method = getattr(request, "method", None)
        request_id = getattr(getattr(request, "state", None), "request_id", None)
        ip = _client_ip(request)
        ua = (request.headers.get("user-agent") or None)
        if ua:
            ua = ua[:400]
    meta = redact(metadata)

    # 1) structured log (always)
    log_level = {"warning": logging.WARNING, "critical": logging.ERROR}.get(severity, logging.INFO)
    logger.log(
        log_level,
        "security.audit %s result=%s actor=%s target=%s/%s endpoint=%s rid=%s",
        event_type, result, a_user, target_type, target_id, endpoint, request_id,
        extra={"event_type": event_type, "result": result, "severity": severity,
               "actor_user_id": str(a_id) if a_id else None, "request_id": request_id},
    )

    # 2) persist (best-effort, isolated — never break the request)
    if session is None:
        return
    try:
        row = SecurityAuditEvent(
            id=uuid.uuid4(), event_type=event_type, severity=severity, result=result,
            actor_user_id=a_id, actor_username=a_user, actor_role=a_role,
            target_type=target_type, target_id=(str(target_id) if target_id else None),
            endpoint=endpoint, method=method, request_id=request_id,
            ip_address=ip, user_agent=ua, reason=(reason[:500] if reason else None),
            metadata_json=meta, created_at=_utcnow(),
        )
        session.add(row)
        await session.commit()
    except Exception as exc:  # noqa: BLE001 — audit must never break the request
        logger.warning("security.audit persist failed for %s: %s", event_type, exc)
        try:
            await session.rollback()
        except Exception:  # pragma: no cover
            pass


# --- thin domain wrappers (uniform call sites) ------------------------------

async def log_auth_event(session, *, event_type, result, request=None, actor=None,
                         actor_username=None, reason=None, metadata=None, severity="info"):
    await record(session, event_type=event_type, result=result, severity=severity,
                 request=request, actor=actor, actor_username=actor_username,
                 target_type="user", target_id=getattr(actor, "id", None),
                 reason=reason, metadata=metadata)


async def log_user_admin_event(session, *, event_type, result, request=None, actor=None,
                               target=None, reason=None, metadata=None, severity="info"):
    await record(session, event_type=event_type, result=result, severity=severity,
                 request=request, actor=actor, target_type="user",
                 target_id=getattr(target, "id", None), reason=reason,
                 metadata={**(metadata or {}),
                           **({"target_username": target.username} if target is not None else {})})


async def log_secret_event(session, *, event_type, result, request=None, actor=None,
                           reason=None, metadata=None, severity="info"):
    await record(session, event_type=event_type, result=result, severity=severity,
                 request=request, actor=actor, target_type="secret",
                 reason=reason, metadata=metadata)


async def log_access_denied(session, *, event_type, request=None, actor=None, reason=None,
                            metadata=None):
    await record(session, event_type=event_type, result="denied", severity="warning",
                 request=request, actor=actor, reason=reason, metadata=metadata)


async def log_system_log_access(session, *, result="success", request=None, actor=None):
    await record(session, event_type="BACKEND_LOGS_VIEWED", result=result,
                 severity="info" if result == "success" else "warning",
                 request=request, actor=actor, target_type="system")
