"""Phase 4F provider metadata endpoints.

Static + scriptwriter-registry-driven catalog. Every entry is metadata
only — no secrets, no API keys, no endpoint URLs containing tokens.
Status values:

- ``available``       — provider is implemented + ready (e.g. template).
- ``configured``      — implemented + appears to be configured at the env
                        level. We don't reach out to verify.
- ``not_configured``  — implemented but missing required config (e.g.
                        empty API key field).
- ``not_implemented`` — placeholder; real backend not wired yet.
- ``disabled``        — explicitly turned off.
"""
from __future__ import annotations

import os

from fastapi import APIRouter

from app.schemas.providers import ProviderInfo, ProvidersResponse

router = APIRouter(prefix="/api/v1/providers", tags=["providers"])


def _llm_providers() -> list[ProviderInfo]:
    # We pull the canonical list from the scriptwriter registry so the
    # backend can't drift from the agents side. Network-call gating
    # follows SCRIPTWRITER_ENABLE_NETWORK_CALLS.
    try:
        from agents.scriptwriter.core.registry import known_backends
    except Exception:
        # Defensive: if the agents tree isn't importable in some edge
        # case, fall back to a hard-coded list.
        known = ("template", "mock", "ollama", "vllm", "openai_compatible", "openai", "anthropic", "local_http")
    else:
        known = tuple(known_backends())

    network_enabled = os.environ.get("SCRIPTWRITER_ENABLE_NETWORK_CALLS", "false").lower() == "true"
    selected = os.environ.get("SCRIPTWRITER_BACKEND", "template").strip()

    out: list[ProviderInfo] = []
    for name in known:
        if name == "template":
            out.append(
                ProviderInfo(
                    category="llm",
                    provider_id=name,
                    label="Template (deterministic, no LLM)",
                    backend_type="template",
                    default_model="static-v1",
                    is_local=True,
                    status="available",
                    notes="Default Phase 3G+. Dependency-free.",
                )
            )
            continue
        if name == "mock":
            out.append(
                ProviderInfo(
                    category="llm",
                    provider_id=name,
                    label="Mock LLM",
                    backend_type="mock",
                    default_model="mock-v1",
                    is_local=True,
                    status="available",
                    notes="Test helper; no real LLM call.",
                )
            )
            continue

        # All real-LLM stubs: not_implemented until generation is wired.
        is_local = name in ("ollama", "vllm", "local_http")
        model_env = {
            "ollama": "OLLAMA_MODEL",
            "vllm": "VLLM_MODEL",
            "openai_compatible": "OPENAI_COMPATIBLE_MODEL",
            "openai": "OPENAI_MODEL",
            "anthropic": "ANTHROPIC_MODEL",
            "local_http": "LOCAL_LLM_MODEL",
        }.get(name, "")
        endpoint_env = {
            "ollama": "OLLAMA_BASE_URL",
            "vllm": "VLLM_BASE_URL",
            "openai_compatible": "OPENAI_COMPATIBLE_BASE_URL",
            "local_http": "LOCAL_LLM_URL",
        }.get(name, "")
        api_key_env = {
            "openai": "OPENAI_API_KEY",
            "openai_compatible": "OPENAI_COMPATIBLE_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
        }.get(name, "")

        model = os.environ.get(model_env, "").strip() if model_env else ""
        endpoint_set = bool(os.environ.get(endpoint_env, "").strip()) if endpoint_env else True
        key_set = bool(os.environ.get(api_key_env, "").strip()) if api_key_env else True

        if not network_enabled:
            status = "not_implemented"
        elif endpoint_set and key_set and model:
            status = "configured"
        else:
            status = "not_configured"
        out.append(
            ProviderInfo(
                category="llm",
                provider_id=name,
                label=name.replace("_", " ").title(),
                backend_type=name,
                default_model=model or None,
                is_local=is_local,
                status=status,
                notes=(
                    "Network calls disabled (SCRIPTWRITER_ENABLE_NETWORK_CALLS=false)."
                    if not network_enabled
                    else ""
                ),
            )
        )
    # Sort so the selected one + template come first.
    out.sort(key=lambda p: (p.provider_id != selected, p.provider_id != "template", p.provider_id))
    return out


def _tts_providers() -> list[ProviderInfo]:
    # Phase 3B narrow: only piper is real. Even then, the runtime stays
    # off until piper-tts is installed and a voice is on disk.
    piper_root = os.environ.get("PIPER_MODELS_ROOT", "").strip()
    voice = os.environ.get("TTS_DEFAULT_VOICE", "en_US-amy-medium").strip()
    try:
        import importlib

        importlib.util.find_spec  # noqa: B018
        piper_installed = importlib.util.find_spec("piper") is not None
    except Exception:
        piper_installed = False
    if piper_installed and piper_root:
        piper_status = "configured"
    elif piper_installed:
        piper_status = "not_configured"
    else:
        piper_status = "not_configured"
    return [
        ProviderInfo(
            category="tts",
            provider_id="piper",
            label="Piper (local, CPU)",
            backend_type="piper",
            default_model=voice or None,
            is_local=True,
            status=piper_status,
            notes=(
                "piper-tts runtime not installed."
                if not piper_installed
                else "Set PIPER_MODELS_ROOT and place voice .onnx + .onnx.json."
                if not piper_root
                else "Place voice .onnx + .onnx.json under PIPER_MODELS_ROOT."
            ),
        ),
    ]


def _video_generator_providers() -> list[ProviderInfo]:
    # The lipsync providers from Phase 3A. None are implemented for real
    # generation yet — included for operator visibility + future wiring.
    return [
        ProviderInfo(
            category="video_generator",
            provider_id="sadtalker",
            label="SadTalker (default lip-sync v1)",
            backend_type="sadtalker",
            default_model="sadtalker-v1",
            is_local=True,
            status="not_implemented",
            notes="Phase 3A stub. No real inference yet. GPU required when wired.",
        ),
        ProviderInfo(
            category="video_generator",
            provider_id="musetalk",
            label="MuseTalk (v2)",
            backend_type="musetalk",
            default_model="musetalk-v2",
            is_local=True,
            status="not_implemented",
            notes="Placeholder. GPU required when wired.",
        ),
        ProviderInfo(
            category="video_generator",
            provider_id="wav2lip",
            label="Wav2Lip (fallback)",
            backend_type="wav2lip",
            default_model="wav2lip-v1",
            is_local=True,
            status="not_implemented",
            notes="Placeholder. GPU required when wired.",
        ),
    ]


@router.get("", response_model=ProvidersResponse)
async def list_providers() -> ProvidersResponse:
    return ProvidersResponse(
        llm=_llm_providers(),
        tts=_tts_providers(),
        video_generator=_video_generator_providers(),
    )


@router.get("/llm", response_model=list[ProviderInfo])
async def list_llm_providers() -> list[ProviderInfo]:
    return _llm_providers()


@router.get("/tts", response_model=list[ProviderInfo])
async def list_tts_providers() -> list[ProviderInfo]:
    return _tts_providers()


@router.get("/video-generators", response_model=list[ProviderInfo])
async def list_video_providers() -> list[ProviderInfo]:
    return _video_generator_providers()
