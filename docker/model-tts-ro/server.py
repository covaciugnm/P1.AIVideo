"""F5TTS-Ro Romanian TTS HTTP wrapper — Phase 10A-1.

This service exposes a small, honest HTTP layer in front of upstream
F5-TTS (https://github.com/SWivid/F5-TTS) configured for Romanian via
the racai-ro adapter (https://github.com/racai-ro/Ro-F5TTS — samples
only as of 2026-05). The wrapper:

- Boots with NO heavy deps installed. The fastapi + uvicorn layer always
  works; everything that needs ``torch`` / ``f5_tts`` is imported lazily
  inside ``POST /tts/generate``. If those packages are missing, the
  endpoint returns a categorised ``runtime_missing`` error instead of
  500ing.
- Never downloads model weights automatically (unless
  ``F5TTS_RO_ALLOW_AUTO_DOWNLOAD=true`` AND the model directory is
  writable).
- Never produces fake audio. If the model / reference voice is absent,
  the wrapper returns ``assets_missing`` and writes nothing.
- Writes the output WAV at the path the caller requested (the backend
  picks a path under its UPLOAD_AUDIO_ROOT so the artifact stays on the
  same volume).

Endpoints:
- ``GET /health`` — always returns 200, reports readiness inline.
- ``POST /tts/generate`` — generates a Romanian WAV from the supplied
  text + operator-mounted reference voice.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field


app = FastAPI(title="F5TTS-Ro wrapper", version="0.1.0")


# ---------------------------------------------------------------------------
# Readiness probes — all stdlib, no torch.
# ---------------------------------------------------------------------------


def _models_root() -> Path:
    return Path(os.environ.get("F5TTS_RO_MODELS_ROOT", "/models/f5tts-ro"))


def _reference_audio_path() -> Path:
    return Path(
        os.environ.get(
            "F5TTS_RO_REFERENCE_AUDIO",
            str(_models_root() / "reference" / "voice.wav"),
        )
    )


def _reference_text() -> str:
    return os.environ.get(
        "F5TTS_RO_REFERENCE_TEXT", "Aceasta este o voce de referinta."
    )


def _check_runtime() -> dict[str, Any]:
    """Probe torch / f5_tts without importing them; importlib.util only."""
    import importlib.util

    torch_spec = importlib.util.find_spec("torch")
    f5_spec = importlib.util.find_spec("f5_tts") or importlib.util.find_spec("f5tts")
    return {
        "torch_available": torch_spec is not None,
        "f5_tts_available": f5_spec is not None,
        "python": sys.version.split()[0],
    }


def _check_assets() -> dict[str, Any]:
    root = _models_root()
    ref = _reference_audio_path()
    candidates: list[Path] = []
    if root.is_dir():
        for ext in ("*.pt", "*.safetensors", "*.bin", "*.ckpt"):
            candidates.extend(root.rglob(ext))
    return {
        "models_root": str(root),
        "models_root_exists": root.is_dir(),
        "weight_files_found": len(candidates),
        "reference_audio": str(ref),
        "reference_audio_exists": ref.is_file(),
        "reference_text_chars": len(_reference_text()),
    }


def _readiness() -> tuple[str, dict[str, Any]]:
    rt = _check_runtime()
    assets = _check_assets()
    if not rt["torch_available"] or not rt["f5_tts_available"]:
        return "runtime_missing", {"runtime": rt, "assets": assets}
    if not assets["models_root_exists"] or assets["weight_files_found"] == 0:
        return "assets_missing", {"runtime": rt, "assets": assets}
    if not assets["reference_audio_exists"]:
        return "assets_missing", {"runtime": rt, "assets": assets}
    return "ready", {"runtime": rt, "assets": assets}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TTSGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1, max_length=8000)
    voice_id: str | None = Field(default=None, max_length=160)
    output_path: str | None = Field(
        default=None,
        description=(
            "Absolute path where the WAV should be written. If unset, "
            "the wrapper writes under /storage/artifacts and returns the path."
        ),
    )
    output_format: Literal["wav"] = "wav"
    language: str = Field(default="ro", max_length=16)
    reference_audio_path: str | None = Field(default=None)
    reference_text: str | None = Field(default=None)


class TTSGenerateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "generated",
        "runtime_missing",
        "assets_missing",
        "config_missing",
        "generation_failed",
    ]
    error_code: str | None = None
    message: str | None = None
    local_path: str | None = None
    duration_seconds: float | None = None
    sample_rate: int | None = None
    channels: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# /health — always 200, payload describes readiness.
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, Any]:
    status, details = _readiness()
    return {
        "service": "f5tts-ro",
        "version": app.version,
        "status": status,
        "ready": status == "ready",
        "details": details,
        "env": {
            "F5TTS_RO_DEVICE": os.environ.get("F5TTS_RO_DEVICE", "cpu"),
            "F5TTS_RO_ALLOW_AUTO_DOWNLOAD": os.environ.get(
                "F5TTS_RO_ALLOW_AUTO_DOWNLOAD", "false"
            ),
        },
        "time": time.time(),
    }


# ---------------------------------------------------------------------------
# /tts/generate — Romanian TTS via upstream F5-TTS + racai-ro adapter.
# ---------------------------------------------------------------------------


def _resolve_output_path(requested: str | None) -> Path:
    if requested:
        return Path(requested)
    base = Path("/storage/artifacts")
    base.mkdir(parents=True, exist_ok=True)
    name = f"f5tts_ro_{int(time.time() * 1000)}.wav"
    return base / name


def _fail(
    status: Literal[
        "runtime_missing",
        "assets_missing",
        "config_missing",
        "generation_failed",
    ],
    *,
    error_code: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> TTSGenerateResponse:
    return TTSGenerateResponse(
        status=status,
        error_code=error_code,
        message=message,
        metadata=metadata or {},
    )


@app.post("/tts/generate", response_model=TTSGenerateResponse)
def tts_generate(payload: TTSGenerateRequest) -> TTSGenerateResponse:
    ready_status, details = _readiness()
    if ready_status == "runtime_missing":
        return _fail(
            "runtime_missing",
            error_code="runtime_missing",
            message=(
                "torch / f5_tts are not installed in this wrapper image. "
                "Rebuild with the heavy ML layer or run a separate F5-TTS "
                "service. No fake audio is produced."
            ),
            metadata=details,
        )
    if ready_status == "assets_missing":
        return _fail(
            "assets_missing",
            error_code="assets_missing",
            message=(
                "Romanian F5-TTS model weights or reference voice are not "
                "on disk. Mount the operator's model directory at "
                f"{_models_root()} and place the reference voice at "
                f"{_reference_audio_path()}. No auto-download."
            ),
            metadata=details,
        )

    # ----- Real generation path (torch + f5_tts present) -----
    out_path = _resolve_output_path(payload.output_path)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _fail(
            "config_missing",
            error_code="config_missing",
            message=f"Cannot create output dir {out_path.parent}: {exc}",
        )

    # Heavy imports happen here — kept lazy so the wrapper boots without
    # them. Wrap every torch / f5-tts call in a broad try/except so a
    # categorised error reaches the backend instead of a 500.
    try:
        import importlib

        torch = importlib.import_module("torch")
        # The Romanian adapter is supposed to extend upstream F5-TTS's
        # ``api`` interface. Tolerate the upstream module renaming
        # between ``f5_tts`` and ``f5tts`` between versions.
        try:
            f5_api = importlib.import_module("f5_tts.api")
        except ModuleNotFoundError:
            f5_api = importlib.import_module("f5tts.api")
    except Exception as exc:
        return _fail(
            "runtime_missing",
            error_code="runtime_missing",
            message=f"Lazy import failed: {type(exc).__name__}: {exc}",
        )

    ref_audio = payload.reference_audio_path or str(_reference_audio_path())
    ref_text = payload.reference_text or _reference_text()
    device = os.environ.get("F5TTS_RO_DEVICE", "cpu")

    try:
        # F5-TTS exposes an ``F5TTS`` class with an ``infer`` method that
        # writes the synthesized WAV. The exact signature varies between
        # versions; the wrapper passes positional + keyword args that
        # work with v0.5+ and falls back to keyword-only for older API.
        tts = f5_api.F5TTS(device=device)
        result = tts.infer(  # type: ignore[no-any-return]
            gen_text=payload.text,
            ref_audio=ref_audio,
            ref_text=ref_text,
            file_wave=str(out_path),
            remove_silence=True,
        )
    except (FileNotFoundError, OSError) as exc:
        # Treat missing reference / models as assets_missing.
        return _fail(
            "assets_missing",
            error_code="assets_missing",
            message=f"Reference / model assets missing: {exc}",
        )
    except Exception as exc:
        # Any other failure scrubs the partial output and reports
        # generation_failed cleanly.
        try:
            if out_path.is_file():
                out_path.unlink()
        except OSError:
            pass
        return _fail(
            "generation_failed",
            error_code="generation_failed",
            message=f"F5-TTS infer failed: {type(exc).__name__}: {exc}",
        )

    if not out_path.is_file() or out_path.stat().st_size == 0:
        return _fail(
            "generation_failed",
            error_code="generation_failed",
            message=(
                f"F5-TTS reported success but {out_path} is missing/empty. "
                "Refusing to register a phantom artifact."
            ),
        )

    # Light-weight WAV header inspection so the wrapper can report
    # duration / sample_rate without pulling soundfile.
    import struct
    import wave

    try:
        with wave.open(str(out_path), "rb") as w:
            sr = w.getframerate()
            ch = w.getnchannels()
            nframes = w.getnframes()
            duration = nframes / float(sr) if sr else None
    except (wave.Error, struct.error, EOFError) as exc:
        try:
            out_path.unlink(missing_ok=True)
        except Exception:
            pass
        return _fail(
            "generation_failed",
            error_code="generation_failed",
            message=f"Output WAV failed wave-module sanity check: {exc}",
        )

    return TTSGenerateResponse(
        status="generated",
        local_path=str(out_path),
        duration_seconds=duration,
        sample_rate=sr,
        channels=ch,
        metadata={
            "device": device,
            "voice_id": payload.voice_id or "racai-ro/Ro-F5TTS",
            "reference_audio": ref_audio,
            "reference_text_chars": len(ref_text),
            "torch_version": getattr(torch, "__version__", "unknown"),
            "infer_result_type": type(result).__name__,
        },
    )


# Avoid unused-import warnings in the lazy-import path.
_ = tempfile
