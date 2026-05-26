"""/api/v1/secrets/* — DB-backed API key store (Phase 12X).

Right-sidebar Keys page calls these endpoints to list / save / test
operator credentials. Every upsert also pushes the value into
``os.environ`` so the existing adapter code that reads
``os.environ.get(...)`` picks it up immediately.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.core.deps import get_db_session
from app.core.security import require_super_admin
from app.models.user import User
from app.schemas.api_secret import (
    ApiSecretCreate,
    ApiSecretListResponse,
    ApiSecretResponse,
    ApiSecretTestResponse,
    ApiSecretUpdate,
)
from app.services import secrets_service, security_audit_service

router = APIRouter(prefix="/api/v1/secrets", tags=["secrets"])


@router.get("", response_model=ApiSecretListResponse)
async def list_secrets(
    request: Request,
    actor: User | None = Depends(require_super_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ApiSecretListResponse:
    await security_audit_service.log_secret_event(
        session, event_type="SECRET_LIST_VIEWED", result="success",
        request=request, actor=actor)
    rows = await secrets_service.load_all(session)
    return ApiSecretListResponse(
        items=[secrets_service.to_response(r) for r in rows],
        catalog=list(secrets_service.CATALOG),
    )


@router.post("", response_model=ApiSecretResponse, status_code=201)
async def upsert_secret(
    request: ApiSecretCreate,
    session: AsyncSession = Depends(get_db_session),
) -> ApiSecretResponse:
    logger.info("secrets.upsert.start key_name=%s category=%s", request.key_name, request.category)
    row = await secrets_service.upsert_secret(
        session,
        key_name=request.key_name,
        value=request.value,
        description=request.description,
        category=request.category,
    )
    logger.info("secrets.upsert.done key_name=%s", row.key_name)
    return secrets_service.to_response(row)


@router.put("/{key_name}", response_model=ApiSecretResponse)
async def update_secret(
    key_name: str,
    request: ApiSecretUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> ApiSecretResponse:
    row = await secrets_service.upsert_secret(
        session, key_name=key_name, value=request.value
    )
    return secrets_service.to_response(row)


@router.delete("/{key_name}", status_code=204)
async def delete_secret(
    key_name: str,
    request: Request,
    actor: User | None = Depends(require_super_admin),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    ok = await secrets_service.delete_secret(session, key_name)
    if not ok:
        # Audit the failed attempt too (target gone / wrong name). key_name
        # is a non-sensitive identifier; the secret value is never logged.
        await security_audit_service.log_secret_event(
            session, event_type="SECRET_DELETED", result="not_found",
            severity="warning", request=request, actor=actor,
            metadata={"key_name": key_name})
        raise HTTPException(status_code=404, detail="secret not found")
    await security_audit_service.log_secret_event(
        session, event_type="SECRET_DELETED", result="success",
        request=request, actor=actor, metadata={"key_name": key_name})


@router.post("/{key_name}/test", response_model=ApiSecretTestResponse)
async def test_secret(
    key_name: str,
    session: AsyncSession = Depends(get_db_session),
) -> ApiSecretTestResponse:
    logger.info("secrets.test.start key_name=%s", key_name)
    result = await secrets_service.run_probe(session, key_name)
    logger.info("secrets.test.done key_name=%s status=%s", key_name, result.status)
    return result
