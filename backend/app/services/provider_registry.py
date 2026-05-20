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


def _query_ollama_models(base_url: str, timeout: float = 1.5) -> list[str]:
    """Phase 19 — quick GET to Ollama's /api/tags so the LLM provider
    catalog can expose every locally-pulled model in the UI dropdown.
    Returns an empty list on any error (network, timeout, parse) so the
    catalog stays metadata-only and never blocks the request.
    """
    if not base_url:
        return []
    try:
        import json as _json
        import urllib.request as _urllib_request
        with _urllib_request.urlopen(f"{base_url.rstrip('/')}/api/tags", timeout=timeout) as r:
            data = _json.loads(r.read())
        return sorted({m.get("name", "") for m in data.get("models", []) if m.get("name")})
    except Exception:
        return []


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

        # Phase 19 — expose every locally-pulled Ollama model as its OWN
        # provider entry so the UI dropdown shows one row per model
        # (qwen3.6:latest, qwen2.5:7b, llama3.1:8b, …) instead of one
        # generic "ollama" row.
        if name == "ollama" and network_enabled:
            base_url = os.environ.get("OLLAMA_BASE_URL", "").strip()
            models = _query_ollama_models(base_url) if base_url else []
            if models:
                for m in models:
                    safe_id = "ollama_" + m.replace(":", "_").replace(".", "_").replace("/", "_")
                    # Pretty label: family + size hint extracted from tag.
                    ml = m.lower()
                    pretty = f"Ollama · {m}"
                    if "qwen3.6" in ml and "27b" in ml and ("q4" in ml or "4-bit" in ml or "4bit" in ml):
                        pretty = f"Ollama · Qwen 3.6 · 27B · 4-bit GGUF · {m}"
                    elif "qwen3.6" in ml:
                        pretty = f"Ollama · Qwen 3.6 · {m}"
                    elif "qwen3.5" in ml and "9b" in ml and ("q4" in ml or "4-bit" in ml or "4bit" in ml):
                        pretty = f"Ollama · Qwen 3.5 · 9B · 4-bit GGUF · {m}"
                    elif "qwen3.5" in ml:
                        pretty = f"Ollama · Qwen 3.5 · {m}"
                    elif "qwen2.5" in ml:
                        pretty = f"Ollama · Qwen 2.5 · {m}"
                    elif "qwen" in ml:
                        pretty = f"Ollama · Qwen · {m}"
                    elif "llama3.1" in ml:
                        pretty = f"Ollama · Llama 3.1 · {m}"
                    elif "llama" in ml:
                        pretty = f"Ollama · Llama · {m}"
                    elif "nomic-embed" in ml:
                        # Embedding model — skip from script catalog.
                        continue
                    out.append(
                        ProviderInfo(
                            category="llm",
                            provider_id=safe_id,
                            label=pretty,
                            backend_type="ollama",
                            default_model=m,
                            is_local=True,
                            local_or_external="local",  # type: ignore[arg-type]
                            status="configured",  # type: ignore[arg-type]
                            supported_models=[m],
                            requires_network=False,
                            requires_gpu=False,
                            requires_model_files=True,
                            healthcheck_available=True,
                            notes=f"Ollama model {m} — pulled locally.",
                        )
                    )
                continue  # Skip generic "ollama" row when we expose per-model entries.

        out.append(
            ProviderInfo(
                category="llm",
                provider_id=name,
                label=_proper_label(name),
                backend_type=name,
                default_model=model or None,
                is_local=is_local,
                local_or_external="local" if is_local else "external",  # type: ignore[arg-type]
                status=status,  # type: ignore[arg-type]
                supported_models=[model] if model else [],
                requires_network=True,
                requires_gpu=False,
                requires_model_files=is_local,
                healthcheck_available=False,
                notes=note,
            )
        )
        continue

    # Phase 24 — operator chose Qwen3.6 27b as the standing default for all
    # videos (other LLMs stay selectable). Float the configured OLLAMA_MODEL
    # (e.g. qwen3.6:27b-q4) to the very top so the UI prefills it first.
    default_model = os.environ.get("OLLAMA_MODEL", "").strip()

    def _is_preferred_default(p: ProviderInfo) -> bool:
        return bool(
            default_model
            and p.backend_type == "ollama"
            and p.default_model == default_model
        )

    out.sort(
        key=lambda p: (
            not _is_preferred_default(p),
            p.provider_id != selected,
            p.provider_id != "template",
            p.provider_id,
        )
    )
    return out


# ---------------------------------------------------------------------------
# TTS catalog
# ---------------------------------------------------------------------------


def _infer_piper_voice_gender(voice_id: str) -> str | None:
    """Heuristic — Piper voice names embed a speaker token (e.g.
    ``en_US-amy-medium``). Map common Piper speakers to genders so the
    frontend can filter the TTS dropdown by character gender.
    Returns ``None`` when the voice is unknown — UI then never blocks it.
    """
    if not voice_id:
        return None
    speaker = voice_id.lower().split("-")[1] if "-" in voice_id else voice_id.lower()
    female = {"amy", "anya", "alba", "catherine", "kathleen", "kristin",
              "lessac", "libritts_r", "ljspeech", "miriam"}
    male = {"alan", "danny", "joe", "kerstin", "norman", "ryan",
            "thorsten", "kerstin_p"}
    if speaker in female: return "female"
    if speaker in male: return "male"
    return None


def _load_f5tts_ro_voices(models_root: str) -> list[dict]:
    """Phase 20 — load the F5TTS-Ro voice catalog.

    Looks for ``<models_root>/voices.yaml`` and returns a list of voice
    dicts. The catalog file uses a permissive schema (see
    ``models/tts/f5tts-ro/voices.yaml`` for the canonical layout). Each
    voice's reference assets must exist on disk; voices that are
    declared in YAML but whose ref_audio is missing are silently
    dropped so the UI never offers an unusable voice.

    Returns an empty list on any error so the legacy single-row fallback
    in ``_build_tts_providers`` keeps working.
    """
    if not models_root:
        models_root = str(
            Path(__file__).resolve().parents[3] / "models" / "tts" / "f5tts-ro"
        )
    catalog_path = Path(models_root) / "voices.yaml"
    if not catalog_path.exists():
        return []
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        # PyYAML isn't a hard dep; if it's missing we degrade silently
        # to the legacy single-row provider entry.
        return []
    try:
        with catalog_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return []
    voices = data.get("voices") if isinstance(data, dict) else None
    if not isinstance(voices, list):
        return []
    out: list[dict] = []
    for entry in voices:
        if not isinstance(entry, dict):
            continue
        voice_id = (entry.get("id") or "").strip()
        if not voice_id:
            continue
        ref_audio = (entry.get("ref_audio") or "ref_audio.wav").strip()
        ref_text = (entry.get("ref_text") or "ref_text.txt").strip()
        voice_dir = Path(models_root) / "voices" / voice_id
        audio_path = (voice_dir / ref_audio).resolve()
        text_path = (voice_dir / ref_text).resolve()
        # Only emit a voice when both reference files actually exist on
        # disk — otherwise the wrapper will fail every selection.
        if not audio_path.exists() or not text_path.exists():
            continue
        out.append(
            {
                "id": voice_id,
                "label": entry.get("label") or "",
                "language": (entry.get("language") or "ro").lower(),
                "gender": (entry.get("gender") or "neutral").lower(),
                "sample_text": entry.get("sample_text") or "",
                "ref_audio_abs": str(audio_path),
                "ref_text_abs": str(text_path),
                "model_abs": (
                    str((voice_dir / entry["model"]).resolve())
                    if entry.get("model")
                    else ""
                ),
                "description": entry.get("description") or "",
            }
        )
    return out


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
            # Phase 18 — voice gender heuristic from Piper voice name.
            voice_gender=_infer_piper_voice_gender(voice or ""),
        )
    )

    # f5tts_ro — Phase 10A-1 Romanian TTS provider, exposed as an
    # OPTIONAL Docker service (profile: ``tts-ro``). The default light
    # backend never imports torch / f5-tts at module load; readiness is
    # probed entirely via env (no network call here — the status reflects
    # whether ``F5TTS_RO_BASE_URL`` is set + whether the operator-mounted
    # model directory exists).
    #
    # Phase 20 — voice catalog (voices.yaml) drives per-voice provider
    # rows. When the catalog file is present we emit one ProviderInfo
    # per voice (each with language + gender + sample_text +
    # sample_audio_url), filtered by the wrapper's reachability. The
    # legacy single-row "f5tts_ro" provider_id is preserved as an alias
    # by the request-time resolver in app/api/tts.py.
    f5_base = os.environ.get("F5TTS_RO_BASE_URL", "").strip()
    f5_root = os.environ.get("F5TTS_RO_MODELS_ROOT", "").strip()
    f5_voices = _load_f5tts_ro_voices(f5_root)
    if f5_voices:
        # Per-voice rows (Phase 20). Status mirrors the wrapper's
        # configuration — voices.yaml describes voices that ARE on disk
        # so we never emit a row for a missing checkpoint.
        if not f5_base:
            f5_status_per_voice = "not_configured"
            f5_notes_suffix = (
                f"Voice catalog {f5_root!r}/voices.yaml found, but "
                "F5TTS_RO_BASE_URL is unset — start the tts-ro wrapper "
                "service to enable selection."
            )
        else:
            f5_status_per_voice = "configured"
            f5_notes_suffix = (
                f"F5TTS-Ro wrapper at {f5_base!r}; voice catalog at "
                f"{f5_root!r}/voices.yaml."
            )
        for voice in f5_voices:
            voice_id = voice["id"]
            out.append(
                ProviderInfo(
                    category="tts",
                    provider_id=f"f5tts_ro_{voice_id}",
                    label=voice.get("label") or f"F5TTS-Ro · {voice_id}",
                    backend_type="local_http_tts",
                    default_model=voice_id,
                    is_local=True,
                    local_or_external="local",  # type: ignore[arg-type]
                    status=f5_status_per_voice,  # type: ignore[arg-type]
                    supported_models=[voice_id],
                    requires_network=False,
                    requires_gpu=False,
                    requires_model_files=True,
                    healthcheck_available=bool(f5_base),
                    notes=(voice.get("description") or "") + " · " + f5_notes_suffix,
                    docs_url="/docs/runbooks/f5tts-ro-runtime.md",
                    voice_gender=voice.get("gender") or "neutral",
                    language=voice.get("language") or "ro",
                    sample_text=voice.get("sample_text") or "",
                    sample_audio_url=f"/api/v1/providers/tts/f5tts_ro_{voice_id}/sample.wav",
                )
            )
    else:
        # Catalog absent — fall back to the legacy single-row status entry
        # so the operator still sees WHY no F5 voice is selectable.
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
                "unset, and no voices.yaml catalog was found — drop one at "
                f"{f5_root!r}/voices.yaml to expose individual voices."
            )
        else:
            f5_status = "not_configured"
            f5_notes = (
                f"F5TTS_RO_BASE_URL={f5_base!r} but no voices.yaml catalog "
                "found — the per-voice dropdown is empty. Add voices.yaml "
                "under F5TTS_RO_MODELS_ROOT."
            )
        out.append(
            ProviderInfo(
                category="tts",
                provider_id="f5tts_ro",
                label="F5TTS-Ro Romanian (no voices configured)",
                backend_type="local_http_tts",
                default_model=None,
                is_local=True,
                local_or_external="local",  # type: ignore[arg-type]
                status=f5_status,  # type: ignore[arg-type]
                supported_models=[],
                requires_network=False,
                requires_gpu=False,
                requires_model_files=True,
                healthcheck_available=bool(f5_base),
                notes=f5_notes,
                docs_url="/docs/runbooks/f5tts-ro-runtime.md",
                voice_gender="neutral",
                language="ro",
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
    # Phase 12V — full catalog including the new lipsync + txt/img→vid
    # providers. Each entry has an env var pointing at the wrapper URL;
    # when unset the row stays ``not_implemented`` so dropdowns surface
    # the missing wrapper clearly. Operator opts in with
    # ``make docker-<name>-build && make docker-<name>-up``.
    base = [
        ("sadtalker", "SadTalker (talking head v1)", "sadtalker", "sadtalker-v1", True, True, ""),
        ("wav2lip", "Wav2Lip (lipsync, fast)", "wav2lip_http", "wav2lip-gan", True, True, "Phase 12Y wrapper."),
        ("musetalk", "MuseTalk (real-time lipsync)", "musetalk_http", "musetalk-v1.5", True, True, "Phase 12Y wrapper."),
        ("liveportrait", "LivePortrait (motion-driven portrait)", "liveportrait_http", "liveportrait-v1", True, True, "Phase 12Y wrapper."),
        ("echomimic", "EchoMimic-V2 (lipsync + half-body gestures)", "echomimic_http", "echomimic-v2", True, True, "Phase 12V wrapper."),
        ("hallo", "Hallo2 (HD/4K talking head)", "hallo_http", "hallo2", True, True, "Phase 12V wrapper."),
        ("svd", "Stable Video Diffusion (img→vid)", "svd_http", "svd-img2vid-xt", True, True, "Phase 12V wrapper, ~10GB."),
        ("animatediff", "AnimateDiff SDXL (txt→vid)", "animatediff_http", "animatediff-sdxl-motion-v1", True, True, "Phase 12V wrapper."),
        ("ltx_video", "LTX-Video (real-time txt→vid)", "ltx_http", "ltx-video-0.9.1", True, True, "Phase 12V wrapper, ~24GB."),
        ("hunyuan_video", "HunyuanVideo (SOTA txt→vid, 4-bit option)", "hunyuan_http", "hunyuan-video-t2v-720p", True, True, "Phase 12V BIG wrapper, ~60GB → 16GB at int4."),
        ("mochi", "Mochi-1 (Genmo txt→vid, 4-bit option)", "mochi_http", "mochi-1-preview", True, True, "Phase 12V BIG wrapper, ~60GB → 16GB at int4."),
        ("local_http_video", "Local HTTP video (operator endpoint)", "local_http", None, True, False, "Operator runs the worker; speaks HTTP."),
        ("external_video_api", "External video API", "external", None, False, False, "External API; not enabled."),
    ]
    # Phase 12V — promote a video provider to ``configured`` when its
    # ``*_BASE_URL`` env is set (mirror image-generator pattern).
    _ENV_BY_PID = {
        "wav2lip": "WAV2LIP_BASE_URL",
        "musetalk": "MUSETALK_BASE_URL",
        "liveportrait": "LIVEPORTRAIT_BASE_URL",
        "echomimic": "ECHOMIMIC_BASE_URL",
        "hallo": "HALLO_BASE_URL",
        "svd": "SVD_BASE_URL",
        "animatediff": "ANIMATEDIFF_BASE_URL",
        "ltx_video": "LTX_BASE_URL",
        "hunyuan_video": "HUNYUAN_BASE_URL",
        "mochi": "MOCHI_BASE_URL",
    }
    out: list[ProviderInfo] = []
    for pid, label, backend_type, model, local, gpu, note in base:
        docs_url = ""
        status = "not_implemented"
        if pid == "sadtalker":
            status, note, docs_url = _sadtalker_dynamic_status()
        elif pid in _ENV_BY_PID:
            # Phase 12V — env-driven status for new wrappers. If the
            # ``*_BASE_URL`` is set the row becomes ``configured`` (the
            # operator started the wrapper); otherwise stays
            # ``not_implemented`` so the dropdown shows the gap.
            url = os.environ.get(_ENV_BY_PID[pid], "").strip()
            if url:
                status = "configured"
                note = f"Wrapper URL set ({url}). Build + start with `make docker-{pid.replace('_', '')}-up`."
            else:
                note = (
                    f"{label} wrapper not configured. Set {_ENV_BY_PID[pid]} "
                    f"and start the Docker wrapper (`make docker-{pid.replace('_', '')}-up`)."
                )
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
                requires_model_files=gpu and pid in (
                    "sadtalker", "musetalk", "wav2lip", "liveportrait",
                    "echomimic", "hallo", "svd", "animatediff",
                    "ltx_video", "hunyuan_video", "mochi",
                ),
                healthcheck_available=pid == "sadtalker" or pid in _ENV_BY_PID,
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
# Image-generator catalog (Phase 12 — Characters tab)
# ---------------------------------------------------------------------------


# Each entry: (provider_id, label, backend_type, default_model, locality,
# requires_gpu, requires_model_files, env_endpoint, env_api_key,
# supported_models, notes_when_unconfigured, docs_url, warning).
# ``env_endpoint`` is the env var that holds the wrapper URL (for local
# Docker wrappers) OR base API URL (for hosted APIs). When non-empty AND
# present in the environment the provider transitions from
# ``not_configured`` to ``configured``. ``env_api_key`` is checked only
# for hosted-API rows; locals don't need it.
#
# ``mock`` is always ``available`` — it returns deterministic placeholder
# PNGs and is the only provider that runs without operator setup.
_IMAGE_GENERATOR_CATALOG: tuple[dict, ...] = (
    # --- Mock (always available, for dev + CI) ---
    {
        "provider_id": "mock",
        "label": "Mock image generator (deterministic placeholder PNG)",
        "backend_type": "mock",
        "default_model": "mock-v1",
        "locality": "local",
        "requires_gpu": False,
        "requires_model_files": False,
        "env_endpoint": "",
        "env_api_key": "",
        "supported_models": ["mock-v1"],
        "always_available": True,
        "notes": (
            "Returns a deterministic 1024x1024 placeholder PNG. "
            "Useful for tests and the no-credentials dev path."
        ),
        "docs_url": "",
        "warning": "",
    },
    # --- Local GPU wrappers (mirror the model-sadtalker pattern) ---
    {
        "provider_id": "flux_local",
        "label": "FLUX.1 local (open-weights, GPU wrapper) — default",
        "backend_type": "flux_local_http",
        "default_model": "flux.1-schnell",
        "locality": "local",
        "requires_gpu": True,
        "requires_model_files": True,
        "env_endpoint": "FLUX_LOCAL_BASE_URL",
        "env_api_key": "",
        "supported_models": ["flux.1-schnell", "flux.1-dev"],
        "notes": (
            "Black Forest Labs FLUX.1 open weights run via the optional "
            "model-flux Docker wrapper (mirrors the model-sadtalker "
            "pattern). Set FLUX_LOCAL_BASE_URL and FLUX_LOCAL_MODELS_ROOT, "
            "then start the wrapper. No auto-download."
        ),
        "docs_url": "/docs/runbooks/flux-local-runtime.md",
        "warning": "",
    },
    {
        "provider_id": "sd35_local",
        "label": "Stable Diffusion 3.5 Large (local, GPU wrapper)",
        "backend_type": "sd35_local_http",
        "default_model": "stable-diffusion-3.5-large",
        "locality": "local",
        "requires_gpu": True,
        "requires_model_files": True,
        "env_endpoint": "SD35_LOCAL_BASE_URL",
        "env_api_key": "",
        "supported_models": [
            "stable-diffusion-3.5-large",
            "stable-diffusion-3.5-large-turbo",
            "stable-diffusion-3.5-medium",
        ],
        "notes": (
            "Stability AI SD3.5 open weights run via the optional "
            "model-sd35 Docker wrapper. Set SD35_LOCAL_BASE_URL + "
            "SD35_LOCAL_MODELS_ROOT, then start the wrapper. No "
            "auto-download."
        ),
        "docs_url": "/docs/runbooks/sd35-local-runtime.md",
        "warning": "",
    },
    {
        "provider_id": "sdxl_local",
        "label": "Stable Diffusion XL (local, GPU wrapper)",
        "backend_type": "sdxl_local_http",
        "default_model": "sdxl-base-1.0",
        "locality": "local",
        "requires_gpu": True,
        "requires_model_files": True,
        "env_endpoint": "SDXL_LOCAL_BASE_URL",
        "env_api_key": "",
        "supported_models": ["sdxl-base-1.0", "sdxl-turbo", "sdxl-lightning"],
        "notes": (
            "SDXL via a local Docker wrapper. Lighter VRAM than FLUX/SD3.5 "
            "(~10GB) — a viable alternative on smaller GPUs."
        ),
        "docs_url": "/docs/runbooks/sdxl-local-runtime.md",
        "warning": "",
    },
    {
        "provider_id": "comfyui_local",
        "label": "ComfyUI workflow runner (local)",
        "backend_type": "comfyui_local_http",
        "default_model": "",
        "locality": "local",
        "requires_gpu": True,
        "requires_model_files": True,
        "env_endpoint": "COMFYUI_BASE_URL",
        "env_api_key": "",
        "supported_models": [],
        "notes": (
            "ComfyUI exposed via its /prompt JSON API. Lets the operator "
            "load arbitrary workflows (FLUX, SD3.5, SDXL, inpainting, "
            "controlnet, ipadapter for reference-image conditioning)."
        ),
        "docs_url": "/docs/runbooks/comfyui-runtime.md",
        "warning": "",
    },
    {
        "provider_id": "a1111_local",
        "label": "AUTOMATIC1111 WebUI (local)",
        "backend_type": "a1111_local_http",
        "default_model": "",
        "locality": "local",
        "requires_gpu": True,
        "requires_model_files": True,
        "env_endpoint": "A1111_BASE_URL",
        "env_api_key": "",
        "supported_models": [],
        "notes": (
            "Stable Diffusion WebUI's /sdapi/v1 endpoints. Wide ecosystem; "
            "useful for legacy SD checkpoints + popular extensions."
        ),
        "docs_url": "https://github.com/AUTOMATIC1111/stable-diffusion-webui/wiki/API",
        "warning": "",
    },
    # --- Hosted APIs (HTTPS, single env API key) ---
    {
        "provider_id": "flux_bfl_api",
        "label": "FLUX BFL hosted API (api.bfl.ml)",
        "backend_type": "flux_bfl_api",
        "default_model": "flux-pro-1.1",
        "locality": "external",
        "requires_gpu": False,
        "requires_model_files": False,
        "env_endpoint": "",
        "env_api_key": "FLUX_BFL_API_KEY",
        "supported_models": [
            "flux-pro-1.1",
            "flux-pro",
            "flux-dev",
            "flux-pro-1.1-ultra",
        ],
        "notes": (
            "Black Forest Labs official hosted API. Set FLUX_BFL_API_KEY. "
            "Supports text-to-image and image-reference (ultra/pro)."
        ),
        "docs_url": "https://docs.bfl.ml/",
        "warning": "Outbound HTTPS; review data-residency before sending operator content.",
    },
    {
        "provider_id": "stability_api",
        "label": "Stability AI hosted (SD3.5 Large / Ultra)",
        "backend_type": "stability_api",
        "default_model": "stable-image-ultra",
        "locality": "external",
        "requires_gpu": False,
        "requires_model_files": False,
        "env_endpoint": "",
        "env_api_key": "STABILITY_API_KEY",
        "supported_models": [
            "stable-image-ultra",
            "stable-image-core",
            "sd3.5-large",
            "sd3.5-large-turbo",
        ],
        "notes": "Stability AI cloud. Set STABILITY_API_KEY.",
        "docs_url": "https://platform.stability.ai/docs/api-reference",
        "warning": "Outbound HTTPS; review data-residency.",
    },
    {
        "provider_id": "replicate_api",
        "label": "Replicate.com (multi-model hosted)",
        "backend_type": "replicate_api",
        "default_model": "black-forest-labs/flux-schnell",
        "locality": "external",
        "requires_gpu": False,
        "requires_model_files": False,
        "env_endpoint": "",
        "env_api_key": "REPLICATE_API_TOKEN",
        "supported_models": [
            "black-forest-labs/flux-schnell",
            "black-forest-labs/flux-dev",
            "stability-ai/stable-diffusion-3.5-large",
            "stability-ai/sdxl",
        ],
        "notes": "Replicate hosts FLUX + SD3.5 + many community models. Set REPLICATE_API_TOKEN.",
        "docs_url": "https://replicate.com/docs",
        "warning": "Outbound HTTPS.",
    },
    {
        "provider_id": "fal_api",
        "label": "fal.ai (fast hosted inference)",
        "backend_type": "fal_api",
        "default_model": "fal-ai/flux/schnell",
        "locality": "external",
        "requires_gpu": False,
        "requires_model_files": False,
        "env_endpoint": "",
        "env_api_key": "FAL_KEY",
        "supported_models": [
            "fal-ai/flux/schnell",
            "fal-ai/flux/dev",
            "fal-ai/flux-pro",
            "fal-ai/stable-diffusion-v35-large",
        ],
        "notes": "fal.ai cloud — optimised for low-latency. Set FAL_KEY.",
        "docs_url": "https://fal.ai/docs",
        "warning": "Outbound HTTPS.",
    },
    {
        "provider_id": "together_api",
        "label": "together.ai (FLUX + community models)",
        "backend_type": "together_api",
        "default_model": "black-forest-labs/FLUX.1-schnell",
        "locality": "external",
        "requires_gpu": False,
        "requires_model_files": False,
        "env_endpoint": "",
        "env_api_key": "TOGETHER_API_KEY",
        "supported_models": [
            "black-forest-labs/FLUX.1-schnell",
            "black-forest-labs/FLUX.1-pro",
            "black-forest-labs/FLUX.1-dev",
        ],
        "notes": "together.ai hosts FLUX. Set TOGETHER_API_KEY.",
        "docs_url": "https://docs.together.ai/",
        "warning": "Outbound HTTPS.",
    },
    {
        "provider_id": "openai_dalle3",
        "label": "OpenAI DALL·E 3",
        "backend_type": "openai_dalle3",
        "default_model": "dall-e-3",
        "locality": "external",
        "requires_gpu": False,
        "requires_model_files": False,
        "env_endpoint": "",
        "env_api_key": "OPENAI_API_KEY",
        "supported_models": ["dall-e-3", "dall-e-2"],
        "notes": "OpenAI Images endpoint. Reuses OPENAI_API_KEY.",
        "docs_url": "https://platform.openai.com/docs/guides/images",
        "warning": "Outbound HTTPS; no reference-image conditioning on dall-e-3.",
    },
    {
        "provider_id": "ideogram_api",
        "label": "Ideogram (text rendering specialist)",
        "backend_type": "ideogram_api",
        "default_model": "ideogram-v2",
        "locality": "external",
        "requires_gpu": False,
        "requires_model_files": False,
        "env_endpoint": "",
        "env_api_key": "IDEOGRAM_API_KEY",
        "supported_models": ["ideogram-v2", "ideogram-v2-turbo", "ideogram-v1"],
        "notes": "Ideogram cloud. Set IDEOGRAM_API_KEY.",
        "docs_url": "https://developer.ideogram.ai/",
        "warning": "Outbound HTTPS.",
    },
    {
        "provider_id": "recraft_api",
        "label": "Recraft (design + illustration)",
        "backend_type": "recraft_api",
        "default_model": "recraftv3",
        "locality": "external",
        "requires_gpu": False,
        "requires_model_files": False,
        "env_endpoint": "",
        "env_api_key": "RECRAFT_API_KEY",
        "supported_models": ["recraftv3", "recraftv2"],
        "notes": "Recraft cloud. Set RECRAFT_API_KEY.",
        "docs_url": "https://www.recraft.ai/docs",
        "warning": "Outbound HTTPS.",
    },
    {
        "provider_id": "vertex_imagen3",
        "label": "Google Vertex AI — Imagen 3",
        "backend_type": "vertex_imagen3",
        "default_model": "imagen-3.0-generate-002",
        "locality": "external",
        "requires_gpu": False,
        "requires_model_files": False,
        "env_endpoint": "VERTEX_AI_PROJECT_ID",
        "env_api_key": "GOOGLE_APPLICATION_CREDENTIALS",
        "supported_models": [
            "imagen-3.0-generate-002",
            "imagen-3.0-fast-generate-001",
        ],
        "notes": (
            "Google Cloud Vertex AI Imagen 3. Set VERTEX_AI_PROJECT_ID + "
            "VERTEX_AI_LOCATION + GOOGLE_APPLICATION_CREDENTIALS (path "
            "to service-account JSON)."
        ),
        "docs_url": "https://cloud.google.com/vertex-ai/generative-ai/docs/image",
        "warning": "Requires GCP service account; outbound HTTPS.",
    },
    {
        "provider_id": "midjourney_unofficial",
        "label": "Midjourney (unofficial proxy — fragile)",
        "backend_type": "midjourney_proxy",
        "default_model": "midjourney-v6",
        "locality": "external",
        "requires_gpu": False,
        "requires_model_files": False,
        "env_endpoint": "MIDJOURNEY_PROXY_URL",
        "env_api_key": "MIDJOURNEY_PROXY_TOKEN",
        "supported_models": ["midjourney-v6", "midjourney-v5.2"],
        "notes": (
            "Unofficial Discord-bot proxy (e.g. midjourney-proxy). "
            "Set MIDJOURNEY_PROXY_URL + MIDJOURNEY_PROXY_TOKEN. No "
            "official API exists; this path is fragile by design."
        ),
        "docs_url": "https://github.com/novicezk/midjourney-proxy",
        "warning": (
            "Midjourney has no official API. The proxy depends on "
            "Discord bot account ToS. Use at your own risk."
        ),
    },
)


def _build_image_generator_providers() -> list[ProviderInfo]:
    """Build the image-generator catalog (Phase 12).

    Metadata-only — no provider is actually invoked here. Status is
    derived from env vars + the always-available mock. The merge with
    operator overrides from ``feature_providers`` (Phase 12 DB table)
    happens later in the request lifecycle via
    :func:`apply_feature_provider_overrides`; the base catalog never
    blocks on DB I/O.
    """
    selected = os.environ.get("IMAGE_GENERATOR_BACKEND", "flux_local").strip()
    out: list[ProviderInfo] = []
    for entry in _IMAGE_GENERATOR_CATALOG:
        pid = entry["provider_id"]
        always_available = entry.get("always_available", False)
        if always_available:
            status = "available"
            notes = entry["notes"]
        else:
            endpoint_env = entry["env_endpoint"]
            key_env = entry["env_api_key"]
            endpoint_set = bool(os.environ.get(endpoint_env, "").strip()) if endpoint_env else False
            key_set = bool(os.environ.get(key_env, "").strip()) if key_env else False
            # For local-GPU wrappers: endpoint URL is enough; key is N/A.
            # For hosted APIs: key alone is enough (no separate endpoint
            # env required since the SDK/URL is baked into the adapter).
            # ComfyUI / A1111 / FLUX_LOCAL / SD35_LOCAL / SDXL_LOCAL: need endpoint.
            # Vertex / Midjourney: need BOTH endpoint and key.
            need_both = pid in ("vertex_imagen3", "midjourney_unofficial")
            need_endpoint_only = entry["locality"] == "local"
            need_key_only = (
                entry["locality"] == "external" and not need_both
            )
            configured = False
            if need_both:
                configured = endpoint_set and key_set
            elif need_endpoint_only:
                configured = endpoint_set
            elif need_key_only:
                configured = key_set
            status = "configured" if configured else "not_configured"
            notes = entry["notes"]
        out.append(
            ProviderInfo(
                category="image_generator",
                provider_id=pid,
                label=entry["label"],
                backend_type=entry["backend_type"],
                default_model=entry["default_model"] or None,
                is_local=(entry["locality"] == "local"),
                local_or_external=entry["locality"],  # type: ignore[arg-type]
                status=status,  # type: ignore[arg-type]
                supported_models=list(entry["supported_models"]),
                requires_network=(entry["locality"] == "external"),
                requires_gpu=entry["requires_gpu"],
                requires_model_files=entry["requires_model_files"],
                healthcheck_available=not always_available
                and status in ("configured", "available"),
                notes=notes,
                warning=entry["warning"],
                docs_url=entry["docs_url"],
            )
        )
    # Selected provider first (so the dropdown defaults to it), then
    # mock, then alphabetical for the remainder.
    out.sort(
        key=lambda p: (
            p.provider_id != selected,
            p.provider_id != "mock",
            p.provider_id,
        )
    )
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


_BUILDERS = {
    "llm": _build_llm_providers,
    "tts": _build_tts_providers,
    "video_generator": _build_video_providers,
    "audio_processor": _build_audio_processor_providers,
    "image_processor": _build_image_processor_providers,
    "image_generator": _build_image_generator_providers,
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


def resolve_f5tts_ro_voice(provider_id: str) -> dict | None:
    """Phase 20 — resolve an ``f5tts_ro_<voice_id>`` provider_id (or the
    legacy ``f5tts_ro`` alias) to the voice dict from ``voices.yaml``.
    Returns ``None`` when the catalog is empty or the voice id doesn't
    match. Callers can use the returned dict's ``ref_audio_abs``,
    ``ref_text_abs``, and ``model_abs`` (may be empty) to drive the
    wrapper request.
    """
    f5_root = os.environ.get("F5TTS_RO_MODELS_ROOT", "").strip()
    voices = _load_f5tts_ro_voices(f5_root)
    if not voices:
        return None
    if provider_id == "f5tts_ro":
        # Legacy alias — default to the first voice in the catalog so
        # pre-Phase-20 jobs still resolve to a real voice.
        default = os.environ.get(
            "F5TTS_RO_DEFAULT_VOICE", voices[0]["id"]
        ).strip()
        match = next((v for v in voices if v["id"] == default), None)
        return match or voices[0]
    if provider_id.startswith("f5tts_ro_"):
        wanted = provider_id[len("f5tts_ro_"):]
        return next((v for v in voices if v["id"] == wanted), None)
    return None


def known_categories() -> tuple[str, ...]:
    """The full set of provider categories the registry serves."""
    return tuple(_BUILDERS.keys())


def apply_feature_provider_overrides(
    catalog: list[ProviderInfo],
    overrides: dict[tuple[str, str], dict],
) -> list[ProviderInfo]:
    """Merge operator overrides from the ``feature_providers`` DB table
    into a catalog snapshot.

    ``overrides`` keys: ``(category, provider_id)``. Values may carry:
        ``enabled`` (bool): when ``False`` and the code status is
            ``available`` / ``configured``, we downgrade to ``disabled``.
        ``display_order`` (int): used to re-sort the catalog so the
            operator can promote/demote rows from the Characters /
            Settings UI without touching code.
        ``health_status`` (str): the last result of a real probe (e.g.
            from ``POST /api/v1/providers/.../health-check``); when
            present it replaces the code-derived status.

    The function is pure — it returns a new list. ``overrides`` is
    permitted to reference unknown providers; those entries are
    ignored.
    """
    if not overrides:
        return catalog
    merged: list[tuple[ProviderInfo, int]] = []
    for idx, p in enumerate(catalog):
        ov = overrides.get((p.category, p.provider_id))
        order = idx
        if ov is None:
            merged.append((p, order))
            continue
        new_status = p.status
        new_notes = p.notes
        if ov.get("health_status"):
            new_status = ov["health_status"]
        if ov.get("enabled") is False and new_status in ("available", "configured"):
            new_status = "disabled"
            new_notes = (
                ov.get("operator_notes")
                or "Disabled by operator from the provider registry."
            )
        if ov.get("display_order") is not None:
            order = int(ov["display_order"])
        merged.append(
            (
                p.model_copy(update={"status": new_status, "notes": new_notes}),
                order,
            )
        )
    merged.sort(key=lambda pair: (pair[1], pair[0].provider_id))
    return [p for p, _ in merged]
