"""Provider registry (Phase 6D).

Centralises the operator-facing provider catalog so the LLM, TTS,
video-generator, audio-processor and image-processor categories can be
extended without touching the API layer.

Boundaries:

- This is **metadata only**. Status reflects env config + on-disk
  asset checks; it never executes a provider, never opens a network
  socket, never imports the provider's runtime.
- ``ALLOW_MODEL_AUTODOWNLOAD`` is never honoured — providers stay
  ``not_configured`` until the operator places assets manually.
- API keys and endpoint URLs that may include credentials are never
  surfaced. ``status`` reflects "configured-looking" without exposing
  the secret value.
- Custom providers live on the frontend (localStorage) only; the
  backend exposes the immutable built-in catalog.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from app.schemas.providers import ProviderInfo


# ---------------------------------------------------------------------------
# LLM catalog
# ---------------------------------------------------------------------------


# Phase 8E — proper-noun label overrides so the operator UI shows
# "OpenAI" / "vLLM" / "HTTP" instead of `.title()`-mangled spellings.
_LLM_LABEL_OVERRIDES: dict[str, str] = {
    "openai": "OpenAI",
    "openai_compatible": "OpenAI-compatible API",
    "anthropic": "Anthropic",
    "ollama": "Ollama",
    "vllm": "vLLM",
    "local_http": "Local HTTP",
}


def _proper_label(name: str) -> str:
    if name in _LLM_LABEL_OVERRIDES:
        return _LLM_LABEL_OVERRIDES[name]
    return name.replace("_", " ").title()


def _build_llm_providers() -> list[ProviderInfo]:
    try:
        from agents.scriptwriter.core.registry import known_backends

        known = tuple(known_backends())
    except Exception:
        known = (
            "template",
            "mock",
            "ollama",
            "vllm",
            "openai_compatible",
            "openai",
            "anthropic",
            "local_http",
        )

    network_enabled = (
        os.environ.get("SCRIPTWRITER_ENABLE_NETWORK_CALLS", "false").lower() == "true"
    )
    selected = os.environ.get("SCRIPTWRITER_BACKEND", "template").strip()

    out: list[ProviderInfo] = []

    def _add(
        provider_id: str,
        label: str,
        *,
        backend_type: str,
        default_model: str | None,
        status: str,
        locality: str = "local",
        requires_network: bool = False,
        requires_gpu: bool = False,
        requires_model_files: bool = False,
        notes: str = "",
        warning: str = "",
        docs_url: str = "",
    ) -> None:
        out.append(
            ProviderInfo(
                category="llm",
                provider_id=provider_id,
                label=label,
                backend_type=backend_type,
                default_model=default_model,
                is_local=(locality == "local"),
                local_or_external=locality,  # type: ignore[arg-type]
                status=status,  # type: ignore[arg-type]
                supported_models=[default_model] if default_model else [],
                requires_network=requires_network,
                requires_gpu=requires_gpu,
                requires_model_files=requires_model_files,
                healthcheck_available=False,
                notes=notes,
                warning=warning,
                docs_url=docs_url,
            )
        )

    for name in known:
        if name == "template":
            _add(
                name,
                "Template (deterministic, no LLM)",
                backend_type="template",
                default_model="template-v1",
                status="available",
                notes="Phase 3G default. Dependency-free.",
            )
            continue
        if name == "mock":
            _add(
                name,
                "Mock LLM",
                backend_type="mock",
                default_model="mock-v1",
                status="available",
                notes="Test helper; no real LLM call.",
            )
            continue

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
        endpoint_set = (
            bool(os.environ.get(endpoint_env, "").strip()) if endpoint_env else True
        )
        key_set = bool(os.environ.get(api_key_env, "").strip()) if api_key_env else True

        if not network_enabled:
            status = "not_implemented"
            note = "Network calls disabled (SCRIPTWRITER_ENABLE_NETWORK_CALLS=false)."
        elif endpoint_set and key_set and model:
            status = "configured"
            note = ""
        else:
            status = "not_configured"
            note = "Set the provider's env vars to enable."

        _add(
            name,
            _proper_label(name),
            backend_type=name,
            default_model=model or None,
            status=status,
            locality="local" if is_local else "external",
            requires_network=True,
            requires_gpu=False,
            requires_model_files=is_local,
            notes=note,
        )

    out.sort(key=lambda p: (p.provider_id != selected, p.provider_id != "template", p.provider_id))
    return out


# ---------------------------------------------------------------------------
# TTS catalog
# ---------------------------------------------------------------------------


def _build_tts_providers() -> list[ProviderInfo]:
    out: list[ProviderInfo] = []

    # piper — full readiness ladder (matches /api/v1/tts/generate).
    try:
        piper_installed = importlib.util.find_spec("piper") is not None
    except Exception:
        piper_installed = False
    piper_root = (
        os.environ.get("PIPER_MODELS_ROOT", "").strip()
        or os.environ.get("TTS_MODELS_ROOT", "").strip()
    )
    voice = os.environ.get("TTS_DEFAULT_VOICE", "en_US-amy-medium").strip()
    if not piper_installed:
        piper_status = "not_configured"
        piper_notes = "piper-tts runtime not installed. Run `pip install piper-tts`."
    elif not piper_root:
        piper_status = "not_configured"
        piper_notes = "Set PIPER_MODELS_ROOT (or TTS_MODELS_ROOT) and place voice files."
    else:
        root = Path(piper_root)
        if (root / f"{voice}.onnx").is_file() and (root / f"{voice}.onnx.json").is_file():
            piper_status = "available"
            piper_notes = f"Ready. Voice {voice!r} found under {piper_root}."
        else:
            piper_status = "configured"
            piper_notes = (
                f"Voice files for {voice!r} not found under {piper_root}. "
                "Place .onnx + .onnx.json manually — no auto-download."
            )
    out.append(
        ProviderInfo(
            category="tts",
            provider_id="piper",
            label="Piper (local, CPU)",
            backend_type="piper",
            default_model=voice or None,
            is_local=True,
            local_or_external="local",
            status=piper_status,  # type: ignore[arg-type]
            supported_models=[voice] if voice else [],
            requires_network=False,
            requires_gpu=False,
            requires_model_files=True,
            healthcheck_available=True,
            notes=piper_notes,
            docs_url="https://github.com/rhasspy/piper",
        )
    )

    # f5tts_ro — Phase 10A-1 Romanian TTS provider, exposed as an
    # OPTIONAL Docker service (profile: ``tts-ro``). The default light
    # backend never imports torch / f5-tts at module load; readiness is
    # probed entirely via env (no network call here — the status reflects
    # whether ``F5TTS_RO_BASE_URL`` is set + whether the operator-mounted
    # model directory exists).
    f5_base = os.environ.get("F5TTS_RO_BASE_URL", "").strip()
    f5_root = os.environ.get("F5TTS_RO_MODELS_ROOT", "").strip()
    f5_voice = os.environ.get("F5TTS_RO_DEFAULT_VOICE", "ro_default").strip()
    if not f5_base and not f5_root:
        f5_status = "not_implemented"
        f5_notes = (
            "F5TTS-Ro service not configured. Build & start the optional "
            "tts-ro Docker service (`make docker-tts-ro-build && "
            "make docker-tts-ro-up`) and set F5TTS_RO_BASE_URL — no "
            "auto-download. See docs/runbooks/f5tts-ro-runtime.md."
        )
    elif not f5_base:
        f5_status = "not_configured"
        f5_notes = (
            f"F5TTS_RO_MODELS_ROOT={f5_root!r} but F5TTS_RO_BASE_URL is "
            "unset — the backend reaches the model only via the optional "
            "tts-ro HTTP wrapper. Start the tts-ro service and set the URL."
        )
    elif not f5_root:
        f5_status = "configured"
        f5_notes = (
            f"F5TTS_RO_BASE_URL={f5_base!r}; F5TTS_RO_MODELS_ROOT unset. "
            "The wrapper service should mount the operator's Romanian "
            "model directory (./models/tts/f5tts-ro by default)."
        )
    else:
        # Operator has wired both URL + models root. The actual readiness
        # is reported by the tts-ro service /health endpoint; the
        # backend catalog merely marks the operator's intent.
        f5_status = "available"
        f5_notes = (
            f"F5TTS-Ro wrapper at {f5_base!r}, model root {f5_root!r}. "
            "Real readiness depends on the wrapper /health endpoint."
        )
    out.append(
        ProviderInfo(
            category="tts",
            provider_id="f5tts_ro",
            label="F5TTS-Ro Romanian (optional service)",
            backend_type="local_http_tts",
            default_model=f5_voice or None,
            is_local=True,
            local_or_external="local",
            status=f5_status,  # type: ignore[arg-type]
            supported_models=[f5_voice] if f5_voice else [],
            requires_network=False,
            # F5-TTS upstream uses torch; the Romanian adapter inherits
            # that requirement. CPU-only inference is supported but slow.
            requires_gpu=False,
            requires_model_files=True,
            healthcheck_available=bool(f5_base),
            notes=f5_notes,
            warning=(
                "Romanian TTS via cdorob/f5-tts-romanian (MIT). Operator "
                "must mount the cdorob checkpoint at "
                "models/tts/f5tts-ro/model/model_last.pt + vocab.txt, "
                "plus a synthetic reference WAV + matching transcript at "
                "models/tts/f5tts-ro/reference/."
            ),
            docs_url="/docs/runbooks/f5tts-ro-runtime.md",
        )
    )

    # Stubs for additional TTS providers — operator-installable, but the
    # backend speaks only metadata until a real adapter ships.
    _tts_stub = [
        ("coqui_tts", "Coqui TTS (local, CPU/GPU)", True, False, True, "coqui-ai/TTS — not wired yet."),
        ("xtts", "XTTS v2 (local, GPU)", True, True, True, "Coqui XTTS; deferred to GPU phase."),
        ("styletts", "StyleTTS / StyleTTS-2 (local, GPU)", True, True, True, "Research project; deferred."),
        ("elevenlabs_compatible", "ElevenLabs-compatible (external)", False, False, False, "External API; not enabled."),
        ("openai_compatible_tts", "OpenAI-compatible TTS (external)", False, False, False, "External API; not enabled."),
        ("local_http_tts", "Local HTTP TTS (operator endpoint)", True, False, False, "Operator runs the daemon; not wired."),
    ]
    for pid, label, local, gpu, files, note in _tts_stub:
        out.append(
            ProviderInfo(
                category="tts",
                provider_id=pid,
                label=label,
                backend_type=pid,
                default_model=None,
                is_local=local,
                local_or_external="local" if local else "external",
                status="not_implemented",
                supported_models=[],
                requires_network=not local,
                requires_gpu=gpu,
                requires_model_files=files,
                healthcheck_available=False,
                notes=note,
                warning="No voice cloning of third parties." if pid in ("xtts", "elevenlabs_compatible") else "",
            )
        )
    return out


# ---------------------------------------------------------------------------
# Video-generator catalog (lipsync)
# ---------------------------------------------------------------------------


def _sadtalker_dynamic_status() -> tuple[str, str, str]:
    """Return ``(catalog_status, notes, docs_url)`` for the SadTalker row.

    Phase 7D wired the real torch.cuda call and Phase 11C added the
    GPU-wrapper proxy, so the catalog row must reflect the live
    ``inspect_status()`` rather than a hardcoded ``not_implemented``.
    Importing the provider here is cheap — it does not load torch.
    """
    try:
        from agents.lipsync.providers.sadtalker.provider import SadTalkerProvider

        status_info = SadTalkerProvider().inspect_status()
    except Exception as exc:  # pragma: no cover — defensive
        return (
            "not_implemented",
            "Readiness probe failed: " f"{type(exc).__name__}: {exc}.",
            "/docs/runbooks/sadtalker-runtime.md",
        )

    status = status_info["status"]
    docs_url = "/docs/runbooks/sadtalker-runtime.md"
    if status == "ready":
        wrapper = status_info.get("wrapper_url", "")
        suffix = f" Wrapper: {wrapper}." if wrapper else ""
        return (
            "available",
            "Real inference available (Phase 7D torch path + Phase 11C "
            "wrapper proxy). Gates SADTALKER_ENABLE_REAL_INFERENCE=true + "
            "RUN_REAL_SADTALKER=1 satisfied; weights present; CUDA "
            "visible." + suffix,
            docs_url,
        )
    if status == "not_implemented":
        return (
            "not_implemented",
            "Real-inference gate off — set "
            "SADTALKER_ENABLE_REAL_INFERENCE=true + RUN_REAL_SADTALKER=1 "
            "to enable real generation.",
            docs_url,
        )
    if status == "not_configured":
        return (
            "not_implemented",
            "SADTALKER_MODELS_ROOT is unset; set it in .env.",
            docs_url,
        )
    if status == "assets_missing":
        missing = status_info.get("details", {}).get("assets", {}).get("missing", [])
        return (
            "not_implemented",
            f"Weights missing under SADTALKER_MODELS_ROOT: {len(missing)} file(s).",
            docs_url,
        )
    if status == "runtime_missing":
        return (
            "not_implemented",
            "torch is not importable in this image and "
            "SADTALKER_BASE_URL is not pointing at a reachable wrapper.",
            docs_url,
        )
    if status == "gpu_unavailable":
        return (
            "not_implemented",
            "torch present but no CUDA device visible.",
            docs_url,
        )
    return (status, f"SadTalker provider reports status={status!r}.", docs_url)


def _build_video_providers() -> list[ProviderInfo]:
    base = [
        ("sadtalker", "SadTalker (default v1)", "sadtalker", "sadtalker-v1", True, True, ""),
        ("musetalk", "MuseTalk (v2)", "musetalk", "musetalk-v2", True, True, "Placeholder. GPU required when wired."),
        ("wav2lip", "Wav2Lip (fallback)", "wav2lip", "wav2lip-v1", True, True, "Placeholder. GPU required when wired."),
        ("liveportrait", "LivePortrait (research)", "liveportrait", "liveportrait-v1", True, True, "Phase 6D placeholder; deferred."),
        ("local_http_video", "Local HTTP video (operator endpoint)", "local_http", None, True, False, "Operator runs the worker; speaks HTTP."),
        ("external_video_api", "External video API", "external", None, False, False, "External API; not enabled."),
    ]
    out: list[ProviderInfo] = []
    for pid, label, backend_type, model, local, gpu, note in base:
        docs_url = ""
        status = "not_implemented"
        if pid == "sadtalker":
            status, note, docs_url = _sadtalker_dynamic_status()
        out.append(
            ProviderInfo(
                category="video_generator",
                provider_id=pid,
                label=label,
                backend_type=backend_type,
                default_model=model,
                is_local=local,
                local_or_external="local" if local else "external",
                status=status,
                supported_models=[model] if model else [],
                requires_network=not local,
                requires_gpu=gpu,
                requires_model_files=gpu and pid in ("sadtalker", "musetalk", "wav2lip", "liveportrait"),
                healthcheck_available=pid == "sadtalker",
                notes=note,
                docs_url=docs_url,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Audio-processor catalog (Phase 6D)
# ---------------------------------------------------------------------------


def _ffmpeg_available() -> bool:
    try:
        from app.services.audio_conversion import has_ffmpeg

        return has_ffmpeg()
    except Exception:
        return False


def _build_audio_processor_providers() -> list[ProviderInfo]:
    ffmpeg_ok = _ffmpeg_available()
    ffmpeg_status = "available" if ffmpeg_ok else "not_configured"
    ffmpeg_notes = (
        "ffmpeg + ffprobe available in the backend image (Phase 4F)."
        if ffmpeg_ok
        else "ffmpeg not on PATH. Install at the OS level."
    )
    return [
        ProviderInfo(
            category="audio_processor",
            provider_id="ffmpeg_convert",
            label="ffmpeg — convert to PCM WAV",
            backend_type="ffmpeg",
            default_model=None,
            is_local=True,
            local_or_external="local",
            status=ffmpeg_status,  # type: ignore[arg-type]
            supported_models=[],
            requires_network=False,
            requires_gpu=False,
            requires_model_files=False,
            healthcheck_available=True,
            notes=ffmpeg_notes,
            docs_url="https://ffmpeg.org/",
        ),
        ProviderInfo(
            category="audio_processor",
            provider_id="ffmpeg_loudness_normalize",
            label="ffmpeg — EBU R128 loudnorm",
            backend_type="ffmpeg",
            is_local=True,
            local_or_external="local",
            status="not_implemented",
            requires_network=False,
            requires_gpu=False,
            requires_model_files=False,
            healthcheck_available=False,
            notes="Phase 6D placeholder; loudnorm wiring deferred.",
        ),
        ProviderInfo(
            category="audio_processor",
            provider_id="ffmpeg_trim_silence",
            label="ffmpeg — silenceremove",
            backend_type="ffmpeg",
            is_local=True,
            local_or_external="local",
            status="not_implemented",
            requires_network=False,
            requires_gpu=False,
            requires_model_files=False,
            healthcheck_available=False,
            notes="Phase 6D placeholder; silenceremove wiring deferred.",
        ),
        ProviderInfo(
            category="audio_processor",
            provider_id="future_denoise",
            label="Denoise (placeholder)",
            backend_type="placeholder",
            is_local=True,
            local_or_external="local",
            status="not_implemented",
            requires_network=False,
            requires_gpu=False,
            requires_model_files=True,
            healthcheck_available=False,
            notes="Placeholder for a future noise-suppression tool.",
        ),
        ProviderInfo(
            category="audio_processor",
            provider_id="future_vad",
            label="Voice activity detection (placeholder)",
            backend_type="placeholder",
            is_local=True,
            local_or_external="local",
            status="not_implemented",
            requires_network=False,
            requires_gpu=False,
            requires_model_files=True,
            healthcheck_available=False,
            notes="Placeholder for a future VAD tool.",
        ),
    ]


# ---------------------------------------------------------------------------
# Image-processor catalog (Phase 6D)
# ---------------------------------------------------------------------------


def _build_image_processor_providers() -> list[ProviderInfo]:
    return [
        ProviderInfo(
            category="image_processor",
            provider_id="stdlib_image_validation",
            label="stdlib image validation (PNG / JPEG / WebP)",
            backend_type="stdlib",
            is_local=True,
            local_or_external="local",
            status="available",
            requires_network=False,
            requires_gpu=False,
            requires_model_files=False,
            healthcheck_available=True,
            notes=(
                "Hand-rolled header parser (Phase 3E). No Pillow / OpenCV "
                "dependency."
            ),
        ),
        ProviderInfo(
            category="image_processor",
            provider_id="future_face_cropper",
            label="Face cropper (placeholder)",
            backend_type="placeholder",
            is_local=True,
            local_or_external="local",
            status="not_implemented",
            requires_network=False,
            requires_gpu=False,
            requires_model_files=True,
            healthcheck_available=False,
            notes="Crops to a frontal-face bounding box. Deferred.",
        ),
        ProviderInfo(
            category="image_processor",
            provider_id="future_background_removal",
            label="Background removal (placeholder)",
            backend_type="placeholder",
            is_local=True,
            local_or_external="local",
            status="not_implemented",
            requires_network=False,
            requires_gpu=True,
            requires_model_files=True,
            healthcheck_available=False,
            notes="rembg-style segmenter. GPU acceleration optional.",
        ),
        ProviderInfo(
            category="image_processor",
            provider_id="future_quality_checker",
            label="Quality checker (placeholder)",
            backend_type="placeholder",
            is_local=True,
            local_or_external="local",
            status="not_implemented",
            requires_network=False,
            requires_gpu=False,
            requires_model_files=True,
            healthcheck_available=False,
            notes="Sharpness / exposure / face-front checks. Deferred.",
        ),
        ProviderInfo(
            category="image_processor",
            provider_id="future_identity_guard_extension",
            label="Identity guard extension (placeholder)",
            backend_type="placeholder",
            is_local=True,
            local_or_external="local",
            status="not_implemented",
            requires_network=False,
            requires_gpu=True,
            requires_model_files=True,
            healthcheck_available=False,
            notes=(
                "CLIP-NN style public-figure check. Extends the existing "
                "Phase 3E synthetic-person attestation. Deferred."
            ),
            warning="Compliance-critical when wired.",
        ),
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


_BUILDERS = {
    "llm": _build_llm_providers,
    "tts": _build_tts_providers,
    "video_generator": _build_video_providers,
    "audio_processor": _build_audio_processor_providers,
    "image_processor": _build_image_processor_providers,
}


def list_providers() -> dict[str, list[ProviderInfo]]:
    return {category: builder() for category, builder in _BUILDERS.items()}


def list_providers_by_category(category: str) -> list[ProviderInfo]:
    if category not in _BUILDERS:
        return []
    return _BUILDERS[category]()


def get_provider(category: str, provider_id: str) -> ProviderInfo | None:
    for p in list_providers_by_category(category):
        if p.provider_id == provider_id:
            return p
    return None
