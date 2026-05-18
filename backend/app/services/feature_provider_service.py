"""Feature-provider DB layer — Phase 12.

The code-driven registry in :mod:`app.services.provider_registry` is the
source of truth for provider capabilities, labels and env-var probes.
This service is a thin DB layer that lets the operator override:

- ``enabled`` — force a provider off without a redeploy.
- ``display_order`` — re-rank the catalog from the UI.
- ``health_status`` — persist the result of a real probe so subsequent
  catalog reads carry the last-known state.

All public functions are async + DB-bound and tolerate the table not
existing (returns empty overrides), so an operator on a pre-Phase-12
schema doesn't see provider listings break.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.models.feature_provider import FeatureProvider
from app.schemas.providers import ProviderInfo

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def load_overrides(session: AsyncSession) -> dict[tuple[str, str], dict]:
    """Load all operator overrides keyed by ``(category, provider_id)``.

    Returns ``{}`` when the table is missing — keeps catalog reads
    available during migrations.
    """
    try:
        result = await session.execute(select(FeatureProvider))
    except (OperationalError, ProgrammingError):
        return {}
    out: dict[tuple[str, str], dict] = {}
    for row in result.scalars().all():
        out[(row.category, row.provider_id)] = {
            "enabled": row.enabled,
            "display_order": row.display_order,
            "health_status": row.health_status,
            "operator_notes": row.operator_notes,
        }
    return out


async def upsert_override(
    session: AsyncSession,
    *,
    category: str,
    provider_id: str,
    enabled: bool | None = None,
    display_order: int | None = None,
    health_status: str | None = None,
    operator_notes: str | None = None,
) -> FeatureProvider:
    """Create or update the override row for ``(category, provider_id)``."""
    result = await session.execute(
        select(FeatureProvider).where(
            FeatureProvider.category == category,
            FeatureProvider.provider_id == provider_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = FeatureProvider(
            category=category,
            provider_id=provider_id,
            enabled=True if enabled is None else enabled,
            display_order=100 if display_order is None else display_order,
            health_status=health_status,
            operator_notes=operator_notes,
        )
        session.add(row)
    else:
        if enabled is not None:
            row.enabled = enabled
        if display_order is not None:
            row.display_order = display_order
        if health_status is not None:
            row.health_status = health_status
        if operator_notes is not None:
            row.operator_notes = operator_notes
    if health_status is not None:
        row.last_health_check_at = _utcnow()
    await session.commit()
    await session.refresh(row)
    return row


async def run_health_check(
    session: AsyncSession,
    category: str,
    provider_id: str,
    info: ProviderInfo,
) -> tuple[str, str]:
    """Best-effort health probe.

    The probe is intentionally cheap: it never sends real prompts or
    generates content. For local-HTTP wrappers it does a 2-second
    HEAD-ish reachability check against the env-resolved base URL.
    For hosted APIs it only validates that the credentialing env vars
    are present (we don't burn quota on every operator click). The
    mock provider is always healthy. Returns ``(status, notes)`` and
    persists the result via :func:`upsert_override`.
    """
    if provider_id == "mock":
        await upsert_override(
            session,
            category=category,
            provider_id=provider_id,
            health_status="available",
        )
        return ("available", "Mock provider — always healthy.")

    # Local wrappers: probe the HTTP endpoint.
    local_endpoint_envs = {
        "flux_local": "FLUX_LOCAL_BASE_URL",
        "sd35_local": "SD35_LOCAL_BASE_URL",
        "sdxl_local": "SDXL_LOCAL_BASE_URL",
        "comfyui_local": "COMFYUI_BASE_URL",
        "a1111_local": "A1111_BASE_URL",
    }
    if provider_id in local_endpoint_envs:
        base = os.environ.get(local_endpoint_envs[provider_id], "").strip()
        if not base:
            await upsert_override(
                session,
                category=category,
                provider_id=provider_id,
                health_status="not_configured",
            )
            return ("not_configured", f"{local_endpoint_envs[provider_id]} unset.")
        status, notes = await _http_health(base)
        await upsert_override(
            session,
            category=category,
            provider_id=provider_id,
            health_status=status,
        )
        return (status, notes)

    # Hosted APIs: validate env presence only.
    hosted_keys = {
        "flux_bfl_api": ("FLUX_BFL_API_KEY",),
        "stability_api": ("STABILITY_API_KEY",),
        "replicate_api": ("REPLICATE_API_TOKEN",),
        "fal_api": ("FAL_KEY",),
        "together_api": ("TOGETHER_API_KEY",),
        "openai_dalle3": ("OPENAI_API_KEY",),
        "ideogram_api": ("IDEOGRAM_API_KEY",),
        "recraft_api": ("RECRAFT_API_KEY",),
        "vertex_imagen3": ("VERTEX_AI_PROJECT_ID", "GOOGLE_APPLICATION_CREDENTIALS"),
        "midjourney_unofficial": ("MIDJOURNEY_PROXY_URL", "MIDJOURNEY_PROXY_TOKEN"),
    }
    if provider_id in hosted_keys:
        required = hosted_keys[provider_id]
        missing = [e for e in required if not os.environ.get(e, "").strip()]
        if missing:
            status = "not_configured"
            notes = f"Missing env vars: {', '.join(missing)}."
        else:
            status = "configured"
            notes = "Credentials present; no outbound call attempted by health probe."
        await upsert_override(
            session,
            category=category,
            provider_id=provider_id,
            health_status=status,
        )
        return (status, notes)

    # Non-image categories: fall back to the catalog's own status.
    return (info.status, info.notes)


async def _http_health(base_url: str) -> tuple[str, str]:
    """Best-effort GET on ``{base}/health`` with a 2-second timeout."""
    try:
        import httpx  # local import — httpx is already in the backend deps
    except Exception:
        return ("error", "httpx not installed in this image; cannot probe.")

    url = base_url.rstrip("/") + "/health"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(url)
    except asyncio.TimeoutError:
        return ("error", f"Timeout reaching {url}")
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("provider health probe failed for %s: %s", url, exc)
        return ("error", f"Probe failed: {type(exc).__name__}: {exc}")
    if response.status_code // 100 == 2:
        return ("available", f"Wrapper at {base_url} responded {response.status_code}.")
    return (
        "error",
        f"Wrapper at {base_url} responded HTTP {response.status_code}.",
    )
