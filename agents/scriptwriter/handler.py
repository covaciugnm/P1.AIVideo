"""Scriptwriter DAG handler — Phase 3G.

Routes through the ScriptProvider registry. The default backend is
``template`` (deterministic, dependency-free), preserving every Phase
1–3F test that didn't configure a different provider.

What the handler does:

1. Resolves a ``ScriptProvider`` from ``SCRIPTWRITER_BACKEND`` (env, default
   ``template``).
2. Builds a structured ``ScriptRequest`` from ``DagState``.
3. Calls ``provider.generate()``. Real network calls are gated by
   ``SCRIPTWRITER_ENABLE_NETWORK_CALLS=true`` AND each provider's own
   readiness (Phase 3G non-template providers raise
   ``ProviderNotImplementedError`` so the runner can fall back).
4. Emits an ``ArtifactRef`` carrying the structured script plus a
   content checksum so the DAG runner promotes it to the ``artifacts``
   table.

When a non-template backend returns ``ProviderNotImplementedError`` we
fall back to the template provider to keep the DAG green — a future
phase that activates a real backend will tighten this fallback (or make
it opt-in).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid

from common.enums import ArtifactType, StageName
from common.exceptions import (
    ProviderNotImplementedError,
    StageRejection,
    UnsupportedBackendError,
)
from common.schemas import ArtifactRef, DagState, StageOutput

from agents.scriptwriter.core.provider import (
    ScriptProvider,
    ScriptRequest,
    ScriptResult,
)
from agents.scriptwriter.core.registry import resolve as resolve_provider

log = logging.getLogger(__name__)


def _stub_uri(job_id: uuid.UUID, filename: str) -> str:
    return f"s3://aivideo-jobs/{job_id}/{filename}"


def _backend_name() -> str:
    return os.environ.get("SCRIPTWRITER_BACKEND", "template")


def _network_calls_enabled() -> bool:
    return os.environ.get("SCRIPTWRITER_ENABLE_NETWORK_CALLS", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _build_request(state: DagState) -> ScriptRequest:
    return ScriptRequest(
        job_id=state.job_id,
        brief=state.brief,
        script_text=state.script_text,
        target_duration_seconds=state.target_duration_seconds,
        language="en",
        safety_constraints=[],
        metadata={
            "voice_mode": state.voice_mode,
            "face_mode": state.face_mode,
        },
    )


def _select_provider() -> tuple[ScriptProvider, str]:
    """Resolve the configured provider, or fall back to template.

    Returns ``(provider, selected_backend_name)`` — the second element is
    the name that was actually used, which may differ from
    ``SCRIPTWRITER_BACKEND`` if we fell back to ``template``.
    """
    configured = _backend_name()
    try:
        provider = resolve_provider(configured)
    except UnsupportedBackendError:
        log.warning(
            "scriptwriter: SCRIPTWRITER_BACKEND=%r unsupported; using template",
            configured,
        )
        return resolve_provider("template"), "template"

    if configured in ("template", "mock"):
        return provider, configured
    # Real backends require explicit opt-in via SCRIPTWRITER_ENABLE_NETWORK_CALLS.
    if not _network_calls_enabled():
        log.info(
            "scriptwriter: %s configured but SCRIPTWRITER_ENABLE_NETWORK_CALLS "
            "is false; using template",
            configured,
        )
        return resolve_provider("template"), "template"
    return provider, configured


def _structured_script_dict(result: ScriptResult) -> dict:
    return {
        "hook": result.hook,
        "body": result.body,
        "cta": result.cta,
        "full_script": result.full_script,
        "estimated_duration_seconds": result.estimated_duration_seconds,
        "language": result.language,
        "provider": result.provider,
        "model": result.model,
        "prompt_version": result.prompt_version,
        "metadata": result.metadata,
    }


async def run(state: DagState) -> StageOutput:
    if not state.brief.strip():
        raise StageRejection(StageName.scriptwriter.value, "brief is empty")

    provider, selected = _select_provider()
    req = _build_request(state)

    try:
        result = await provider.generate(req)
    except ProviderNotImplementedError as exc:
        # Real provider not ready — fall back to template so the DAG
        # keeps moving. Phase 3G ships only the template as functional.
        log.info(
            "scriptwriter: provider %r not implemented (%s); using template",
            selected,
            exc,
        )
        template = resolve_provider("template")
        result = await template.generate(req)
        selected = "template"

    structured = _structured_script_dict(result)
    payload = json.dumps(structured, sort_keys=True, ensure_ascii=False).encode("utf-8")
    checksum = hashlib.sha256(payload).hexdigest()

    script_ref = ArtifactRef(
        artifact_type=ArtifactType.script.value,
        uri=_stub_uri(state.job_id, "script.json"),
        mime_type="application/json",
        checksum_sha256=checksum,
        size_bytes=len(payload),
        extra={
            "phase": "phase3g",
            "selected_backend": selected,
            "configured_backend": _backend_name(),
            "network_calls_enabled": _network_calls_enabled(),
            "structured_script": structured,
        },
    )

    return StageOutput(
        noop=False,
        notes=(
            f"scriptwriter ran via backend={selected!r} "
            f"(configured={_backend_name()!r}); structured script registered."
        ),
        artifacts={"script": script_ref},
    )
