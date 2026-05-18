"""Phase 5B Scriptwriter generate endpoint.

POST /api/v1/script/generate

Drives the existing scriptwriter provider registry. The `template`
provider is always available and produces a deterministic structured
script (hook / body / cta). The `ollama` (qwen3.6 default, qwen3:8b
fallback) and `mock` providers are also reachable through the registry.

Network-call providers (`ollama`, `vllm`, `openai_compatible`, `openai`,
`anthropic`, `local_http`) are gated by SCRIPTWRITER_ENABLE_NETWORK_CALLS.
When that flag is false, this endpoint refuses with code
`script_provider_disabled`. When true but the provider isn't actually
reachable, the registry returns ProviderNotImplementedError and we
return `script_provider_unreachable`. The deterministic template path
always works.

Schemas:
- ScriptGenerateRequest — operator inputs.
- ScriptGenerateResponse — structured script + metadata.
- ScriptGenerateError — categorised 503 detail.

Boundaries:
- No model auto-download.
- No external API key in response.
- No secrets echoed back.
- No binary content.
- Metadata-only.
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

logger = logging.getLogger(__name__)
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import ProviderNotImplementedError, UnsupportedBackendError

from app.core.deps import get_db_session

router = APIRouter(prefix="/api/v1/script", tags=["script"])


# Providers that don't reach out to a network endpoint — always allowed.
_LOCAL_DETERMINISTIC = {"template", "mock"}


class ScriptGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brief: str = Field(..., min_length=1, max_length=2000)
    target_duration_seconds: int = Field(..., ge=1, le=600)
    script_text: str | None = Field(default=None, max_length=8000)
    tone: str | None = Field(default=None, max_length=80)
    language: str = Field(default="en", max_length=16)
    provider_id: str = Field(default="template", max_length=80)
    model: str | None = Field(default=None, max_length=160)


class ScriptGenerateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["generated"]
    provider_id: str
    model: str
    hook: str
    body: str
    cta: str
    full_script: str
    estimated_duration_seconds: float
    language: str
    artifact_id: uuid.UUID | None = None  # phase 5B: artifact registration optional
    message: str = ""


class ScriptGenerateError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal[
        "script_provider_not_configured",
        "script_provider_disabled",
        "script_provider_unreachable",
        "script_provider_not_implemented",
        "script_generation_failed",
        # Phase 8G-2 — distinct code for "daemon reachable but selected
        # model not pulled" (Ollama 404 / model_missing path). Lets the
        # frontend show a model-specific operator hint instead of the
        # generic "provider unreachable" message.
        "script_model_missing",
    ]
    message: str
    provider_id: str


def _raise_503(code: str, provider_id: str, message: str) -> None:
    err = ScriptGenerateError(code=code, provider_id=provider_id, message=message)  # type: ignore[arg-type]
    raise HTTPException(status_code=503, detail=err.model_dump())


@router.post(
    "/generate",
    responses={
        201: {"model": ScriptGenerateResponse},
        503: {"model": ScriptGenerateError},
    },
    status_code=201,
)
async def script_generate(
    payload: ScriptGenerateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ScriptGenerateResponse:
    provider_id = payload.provider_id.strip() or "template"
    logger.info(
        "script.generate.start provider=%s model=%s target_dur=%s lang=%s",
        provider_id, payload.model, payload.target_duration_seconds, payload.language,
    )

    # Network-call gate.
    enable_network = os.environ.get(
        "SCRIPTWRITER_ENABLE_NETWORK_CALLS", "false"
    ).lower() == "true"

    if provider_id not in _LOCAL_DETERMINISTIC and not enable_network:
        _raise_503(
            "script_provider_disabled",
            provider_id,
            "Network LLM calls are disabled. Set "
            "SCRIPTWRITER_ENABLE_NETWORK_CALLS=true to allow this provider, "
            "or pick the 'template' provider for the deterministic path.",
        )

    # Resolve provider through the existing registry.
    from agents.scriptwriter.core.registry import resolve as resolve_provider
    from agents.scriptwriter.core.provider import ScriptRequest

    try:
        provider = resolve_provider(provider_id)
    except UnsupportedBackendError as exc:
        _raise_503(
            "script_provider_not_configured",
            provider_id,
            f"Unknown provider {provider_id!r}: {exc}",
        )

    # Inject the operator-supplied model if non-None.
    if payload.model:
        provider.model_name = payload.model

    # Health probe — short-circuit on cleanly-reported not_implemented /
    # not_configured so the operator gets a categorised hint.
    try:
        health = provider.healthcheck()
    except Exception as exc:  # defensive
        _raise_503(
            "script_provider_not_configured",
            provider_id,
            f"Provider healthcheck raised: {type(exc).__name__}: {exc}",
        )

    # ProviderHealthStatus is a str-Enum, accept either str or enum value.
    status_value = getattr(health.status, "value", health.status)

    if status_value == "not_implemented":
        # Ollama / vLLM / OpenAI stubs all land here when network calls
        # are gated off OR no real client is wired.
        _raise_503(
            "script_provider_unreachable" if enable_network else "script_provider_disabled",
            provider_id,
            (health.errors[0] if health.errors else "Provider not implemented.")
            + " Falling back to provider='template' produces a deterministic script.",
        )
    if status_value in ("not_configured", "missing_assets"):
        _raise_503(
            "script_provider_not_configured",
            provider_id,
            health.errors[0] if health.errors else "Provider not configured.",
        )

    # ----- Real generation path -----
    req = ScriptRequest(
        job_id=uuid.uuid4(),  # synthetic — preview only, no job linkage yet
        brief=payload.brief,
        script_text=payload.script_text,
        target_duration_seconds=payload.target_duration_seconds,
        language=payload.language,
        tone=payload.tone,
    )
    try:
        result = await provider.generate(req)
    except ProviderNotImplementedError as exc:
        # Phase 8G + 8G-2 — the Ollama provider raises
        # ProviderNotImplementedError with a categorised prefix when the
        # daemon / model is in a known bad state. Route to the matching
        # ``script_*`` code so the operator sees an actionable hint.
        msg = str(exc)
        if msg.startswith("model_missing:"):
            # Phase 8G-2 — distinct from unreachable. The daemon
            # answered, just doesn't have the requested model pulled.
            code = "script_model_missing"
        elif msg.startswith("unreachable:"):
            code = "script_provider_unreachable"
        elif msg.startswith("malformed_response:"):
            code = "script_generation_failed"
        else:
            code = (
                "script_provider_unreachable"
                if enable_network
                else "script_provider_disabled"
            )
        _raise_503(code, provider_id, msg)
    except Exception as exc:
        _raise_503(
            "script_generation_failed",
            provider_id,
            f"{type(exc).__name__}: {exc}",
        )

    # Note: the artifact registration path exists on the regular DAG. The
    # preview endpoint deliberately doesn't store a script artifact yet
    # (no job is linked) — the operator can copy the structured fields
    # into Create Job. A future phase can opt to persist with a NULL
    # job_id similar to the upload-intake artifacts.
    _ = session  # session reserved for future artifact persistence.

    return ScriptGenerateResponse(
        status="generated",
        provider_id=provider_id,
        model=provider.model_name or "",
        hook=result.hook,
        body=result.body,
        cta=result.cta,
        full_script=result.full_script,
        estimated_duration_seconds=result.estimated_duration_seconds,
        language=result.language,
        artifact_id=None,
        message="Preview-only; copy into Create Job to register an artifact.",
    )
