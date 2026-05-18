"""API secrets service — Phase 12X.

DB-backed credentials store. The startup hook loads every row into
``os.environ`` so adapter code that reads ``os.environ.get(...)``
keeps working unchanged. Upserts push to env immediately.

The "test" endpoint runs a cheap per-provider reachability probe
against the live service. Probes never spend generation quota.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.models.api_secret import ApiSecret
from app.schemas.api_secret import (
    ApiSecretCatalogEntry,
    ApiSecretResponse,
    ApiSecretTestResponse,
    SecretCategory,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Canonical catalog of secrets we know how to test.
# ---------------------------------------------------------------------------


CATALOG: tuple[ApiSecretCatalogEntry, ...] = (
    ApiSecretCatalogEntry(
        key_name="HF_TOKEN",
        description="Hugging Face access token (read). Unlocks gated downloads (FLUX.1, SD3.5).",
        category="huggingface",
        test_probe="GET https://huggingface.co/api/whoami-v2",
    ),
    # --- Image generator API keys ---
    ApiSecretCatalogEntry(
        key_name="FLUX_BFL_API_KEY",
        description="Black Forest Labs hosted FLUX API key. Set via https://api.bfl.ml.",
        category="image_generator",
        test_probe="GET https://api.bfl.ml/v1/get_result (auth header)",
    ),
    ApiSecretCatalogEntry(
        key_name="STABILITY_API_KEY",
        description="Stability AI hosted (SD3.5 Ultra/Large).",
        category="image_generator",
        test_probe="GET https://api.stability.ai/v1/user/account",
    ),
    ApiSecretCatalogEntry(
        key_name="REPLICATE_API_TOKEN",
        description="Replicate.com (hosts FLUX + SD + many community models).",
        category="image_generator",
        test_probe="GET https://api.replicate.com/v1/account",
    ),
    ApiSecretCatalogEntry(
        key_name="FAL_KEY",
        description="fal.ai low-latency hosted inference.",
        category="image_generator",
        test_probe="GET https://fal.run/api/me",
    ),
    ApiSecretCatalogEntry(
        key_name="TOGETHER_API_KEY",
        description="together.ai (FLUX + community models).",
        category="image_generator",
        test_probe="GET https://api.together.xyz/v1/models",
    ),
    ApiSecretCatalogEntry(
        key_name="IDEOGRAM_API_KEY",
        description="Ideogram (text-rendering specialist).",
        category="image_generator",
        test_probe="GET https://api.ideogram.ai/v1/me",
    ),
    ApiSecretCatalogEntry(
        key_name="RECRAFT_API_KEY",
        description="Recraft (design + illustration cloud).",
        category="image_generator",
        test_probe="GET https://external.api.recraft.ai/v1/users/me",
    ),
    ApiSecretCatalogEntry(
        key_name="VERTEX_AI_PROJECT_ID",
        description="Google Cloud project ID for Vertex AI (Imagen 3).",
        category="image_generator",
        test_probe="Non-empty check (full probe requires GOOGLE_APPLICATION_CREDENTIALS too)",
    ),
    ApiSecretCatalogEntry(
        key_name="GOOGLE_APPLICATION_CREDENTIALS",
        description="Path to GCP service-account JSON for Vertex AI Imagen 3.",
        category="image_generator",
        test_probe="File exists + parsable JSON",
    ),
    ApiSecretCatalogEntry(
        key_name="MIDJOURNEY_PROXY_URL",
        description="Unofficial Midjourney proxy base URL (Discord bot).",
        category="image_generator",
        test_probe="GET <url>/mj/health",
    ),
    ApiSecretCatalogEntry(
        key_name="MIDJOURNEY_PROXY_TOKEN",
        description="Auth token for the Midjourney proxy.",
        category="image_generator",
        test_probe="Non-empty check",
    ),
    # --- LLM ---
    ApiSecretCatalogEntry(
        key_name="OPENAI_API_KEY",
        description="OpenAI (LLM + DALL·E 3 + Whisper).",
        category="llm",
        test_probe="GET https://api.openai.com/v1/models",
    ),
    ApiSecretCatalogEntry(
        key_name="ANTHROPIC_API_KEY",
        description="Anthropic Claude API.",
        category="llm",
        test_probe="Header-only check (real probe spends a tiny token quota)",
    ),
    # --- Local wrapper endpoints (URLs, not secrets per se) ---
    ApiSecretCatalogEntry(
        key_name="FLUX_LOCAL_BASE_URL",
        description="Local FLUX GPU wrapper URL (default http://aivideo-model-flux-1:8080).",
        category="local_endpoint",
        test_probe="GET {url}/health",
    ),
    ApiSecretCatalogEntry(
        key_name="SDXL_LOCAL_BASE_URL",
        description="Local SDXL GPU wrapper URL (default http://aivideo-model-sdxl-1:8080).",
        category="local_endpoint",
        test_probe="GET {url}/health",
    ),
    ApiSecretCatalogEntry(
        key_name="SD35_LOCAL_BASE_URL",
        description="Local SD3.5 GPU wrapper URL (default http://aivideo-model-sd35-1:8080).",
        category="local_endpoint",
        test_probe="GET {url}/health",
    ),
    ApiSecretCatalogEntry(
        key_name="COMFYUI_BASE_URL",
        description="ComfyUI HTTP API base URL (operator-managed).",
        category="local_endpoint",
        test_probe="GET {url}/system_stats",
    ),
    ApiSecretCatalogEntry(
        key_name="A1111_BASE_URL",
        description="AUTOMATIC1111 WebUI API base URL (operator-managed).",
        category="local_endpoint",
        test_probe="GET {url}/sdapi/v1/options",
    ),
    ApiSecretCatalogEntry(
        key_name="F5TTS_RO_BASE_URL",
        description="Optional F5TTS-Ro TTS wrapper URL.",
        category="local_endpoint",
        test_probe="GET {url}/health",
    ),
    ApiSecretCatalogEntry(
        key_name="SADTALKER_BASE_URL",
        description="SadTalker GPU wrapper URL (already running in the dev stack).",
        category="local_endpoint",
        test_probe="GET {url}/health",
    ),
    ApiSecretCatalogEntry(
        key_name="OLLAMA_BASE_URL",
        description="Host-side Ollama daemon (default http://host.docker.internal:11434).",
        category="llm",
        test_probe="GET {url}/api/tags",
    ),
    ApiSecretCatalogEntry(
        key_name="IMAGE_GENERATOR_ENABLE_NETWORK_CALLS",
        description="Master switch: set to ``true`` to let hosted image-generator adapters issue outbound HTTP.",
        category="misc",
        test_probe="String compare; expected ``true`` / ``1`` / ``yes`` to enable.",
    ),
    ApiSecretCatalogEntry(
        key_name="SCRIPTWRITER_ENABLE_NETWORK_CALLS",
        description="Master switch for the LLM scriptwriter to issue outbound HTTP.",
        category="misc",
        test_probe="String compare; expected ``true``.",
    ),
)


CATALOG_MAP: dict[str, ApiSecretCatalogEntry] = {e.key_name: e for e in CATALOG}


# ---------------------------------------------------------------------------
# DB I/O
# ---------------------------------------------------------------------------


async def load_all(session: AsyncSession) -> list[ApiSecret]:
    try:
        result = await session.execute(select(ApiSecret).order_by(ApiSecret.key_name))
    except (OperationalError, ProgrammingError):
        return []
    return list(result.scalars().all())


async def load_into_env(session: AsyncSession) -> int:
    """Push every persisted secret into ``os.environ``. Returns count."""
    rows = await load_all(session)
    for row in rows:
        if row.value:
            os.environ[row.key_name] = row.value
    return len(rows)


async def get_secret(session: AsyncSession, key_name: str) -> ApiSecret | None:
    r = await session.execute(select(ApiSecret).where(ApiSecret.key_name == key_name))
    return r.scalar_one_or_none()


async def upsert_secret(
    session: AsyncSession,
    *,
    key_name: str,
    value: str,
    description: str | None = None,
    category: SecretCategory | None = None,
) -> ApiSecret:
    row = await get_secret(session, key_name)
    if row is None:
        row = ApiSecret(
            key_name=key_name,
            value=value,
            description=description,
            category=category or CATALOG_MAP.get(key_name).category
            if key_name in CATALOG_MAP
            else (category or "misc"),
        )
        session.add(row)
    else:
        row.value = value
        if description is not None:
            row.description = description
        if category is not None:
            row.category = category
    await session.commit()
    await session.refresh(row)
    # Push to env immediately so the next request sees it.
    os.environ[key_name] = value
    return row


async def delete_secret(session: AsyncSession, key_name: str) -> bool:
    row = await get_secret(session, key_name)
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    if key_name in os.environ:
        del os.environ[key_name]
    return True


def to_response(row: ApiSecret) -> ApiSecretResponse:
    return ApiSecretResponse(
        id=row.id,
        key_name=row.key_name,
        value=row.value,
        description=row.description,
        category=row.category or "misc",  # type: ignore[arg-type]
        last_tested_at=row.last_tested_at,
        last_test_status=row.last_test_status,
        last_test_detail=row.last_test_detail,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# ---------------------------------------------------------------------------
# Test probes
# ---------------------------------------------------------------------------


async def _http_probe(
    method: str, url: str, *, headers: dict | None = None, timeout: float = 5.0
) -> tuple[bool, str]:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.request(method, url, headers=headers)
        if r.status_code // 100 == 2:
            return True, f"HTTP {r.status_code}"
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


async def run_probe(
    session: AsyncSession, key_name: str
) -> ApiSecretTestResponse:
    row = await get_secret(session, key_name)
    if row is None or not row.value:
        return ApiSecretTestResponse(
            key_name=key_name,
            status="skipped",
            detail="secret is empty",
            last_tested_at=_utcnow(),
        )
    value = row.value

    ok = False
    detail = ""
    # Dispatch by key — cheap reachability or auth checks, never burns
    # generation quota.
    if key_name == "HF_TOKEN":
        ok, detail = await _http_probe(
            "GET",
            "https://huggingface.co/api/whoami-v2",
            headers={"Authorization": f"Bearer {value}"},
        )
    elif key_name == "FLUX_BFL_API_KEY":
        ok, detail = await _http_probe(
            "GET",
            "https://api.bfl.ml/v1/get_result?id=00000000-0000-0000-0000-000000000000",
            headers={"x-key": value},
        )
        # BFL returns 404 for missing job-id, which still proves the key works.
        if "HTTP 404" in detail or "HTTP 400" in detail:
            ok = True
            detail = "auth header accepted (404 for nonexistent job is expected)"
    elif key_name == "STABILITY_API_KEY":
        ok, detail = await _http_probe(
            "GET",
            "https://api.stability.ai/v1/user/account",
            headers={"Authorization": f"Bearer {value}"},
        )
    elif key_name == "REPLICATE_API_TOKEN":
        ok, detail = await _http_probe(
            "GET",
            "https://api.replicate.com/v1/account",
            headers={"Authorization": f"Bearer {value}"},
        )
    elif key_name == "FAL_KEY":
        ok, detail = await _http_probe(
            "GET",
            "https://rest.alpha.fal.ai/users/me",
            headers={"Authorization": f"Key {value}"},
        )
    elif key_name == "TOGETHER_API_KEY":
        ok, detail = await _http_probe(
            "GET",
            "https://api.together.xyz/v1/models",
            headers={"Authorization": f"Bearer {value}"},
        )
    elif key_name == "IDEOGRAM_API_KEY":
        ok, detail = await _http_probe(
            "GET",
            "https://api.ideogram.ai/manage/api-key",
            headers={"Api-Key": value},
        )
    elif key_name == "RECRAFT_API_KEY":
        ok, detail = await _http_probe(
            "GET",
            "https://external.api.recraft.ai/v1/users/me",
            headers={"Authorization": f"Bearer {value}"},
        )
    elif key_name == "OPENAI_API_KEY":
        ok, detail = await _http_probe(
            "GET",
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {value}"},
        )
    elif key_name == "ANTHROPIC_API_KEY":
        # No free probe — just header validation.
        ok = value.startswith("sk-ant-")
        detail = "key prefix OK" if ok else "expected prefix 'sk-ant-' missing"
    elif key_name == "VERTEX_AI_PROJECT_ID":
        ok = bool(value.strip())
        detail = "non-empty"
    elif key_name == "GOOGLE_APPLICATION_CREDENTIALS":
        from pathlib import Path as _P

        p = _P(value)
        if not p.is_file():
            ok, detail = False, f"file not found: {value}"
        else:
            try:
                import json as _j

                _j.loads(p.read_text(encoding="utf-8"))
                ok, detail = True, f"file readable, size {p.stat().st_size}B"
            except Exception as exc:
                ok, detail = False, f"JSON parse failed: {exc}"
    elif key_name == "MIDJOURNEY_PROXY_URL":
        ok, detail = await _http_probe(
            "GET", value.rstrip("/") + "/mj/health"
        )
    elif key_name in (
        "FLUX_LOCAL_BASE_URL",
        "SDXL_LOCAL_BASE_URL",
        "SD35_LOCAL_BASE_URL",
        "F5TTS_RO_BASE_URL",
        "SADTALKER_BASE_URL",
    ):
        ok, detail = await _http_probe(
            "GET", value.rstrip("/") + "/health"
        )
    elif key_name == "COMFYUI_BASE_URL":
        ok, detail = await _http_probe(
            "GET", value.rstrip("/") + "/system_stats"
        )
    elif key_name == "A1111_BASE_URL":
        ok, detail = await _http_probe(
            "GET", value.rstrip("/") + "/sdapi/v1/sd-models"
        )
    elif key_name == "OLLAMA_BASE_URL":
        ok, detail = await _http_probe(
            "GET", value.rstrip("/") + "/api/tags"
        )
    elif key_name in ("IMAGE_GENERATOR_ENABLE_NETWORK_CALLS", "SCRIPTWRITER_ENABLE_NETWORK_CALLS"):
        ok = value.lower() in ("true", "1", "yes")
        detail = "enabled" if ok else f"disabled (value={value!r})"
    elif key_name == "MIDJOURNEY_PROXY_TOKEN":
        ok = bool(value.strip())
        detail = "non-empty"
    else:
        ok, detail = True, "no built-in probe for this key — saved verbatim"

    # Persist outcome.
    row.last_tested_at = _utcnow()
    row.last_test_status = "ok" if ok else "failed"
    row.last_test_detail = detail
    await session.commit()
    await session.refresh(row)
    return ApiSecretTestResponse(
        key_name=key_name,
        status="ok" if ok else "failed",
        detail=detail,
        last_tested_at=row.last_tested_at,
    )
