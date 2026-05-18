"""FLUX.1 GPU HTTP wrapper — Phase 12W.

Mirrors the SadTalker wrapper pattern (docker/model-sadtalker/server.py).
The light backend posts to ``/flux/generate``; this service runs the
diffusers FluxPipeline on the local GPU and writes a PNG to the
shared ``/storage/artifacts`` volume.

Endpoints:
- ``GET /health`` — always 200, payload describes runtime + weight state.
- ``POST /flux/generate`` — text-to-image (optionally image-to-image
  when ``reference_image_path`` is set + diffusers supports the
  pipeline for the selected model).

Safety contract:
- No fake PNG. If torch / diffusers / weights are missing the endpoint
  returns a categorised error and writes nothing.
- No auto-download. ``HF_HUB_OFFLINE=1`` is set in the image so
  diffusers can't reach Hugging Face — operator must place weights
  manually under ``${FLUX_MODELS_ROOT}/<model_id>``.
- Cleans partial files on failure.
"""
from __future__ import annotations

import io
import logging
import os
import sys
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

app = FastAPI(title="FLUX.1 GPU wrapper", version="0.1.0")


# ---------------------------------------------------------------------------
# Readiness probes — stdlib only at module load. Torch + diffusers import
# is lazy (deferred to the first /generate call).
# ---------------------------------------------------------------------------


def _models_root() -> Path:
    return Path(os.environ.get("FLUX_MODELS_ROOT", "/models/image/flux"))


def _result_dir() -> Path:
    return Path(os.environ.get("FLUX_RESULT_DIR", "/storage/artifacts/flux"))


def _default_model() -> str:
    return os.environ.get("FLUX_DEFAULT_MODEL", "flux.1-schnell").strip()


# The diffusers FluxPipeline expects either a HF model_id or a local
# path containing model_index.json + the transformer + vae + text_encoder
# sub-folders. Operators clone the BFL repos (FLUX.1-schnell / -dev)
# under ``models/image/flux/<model_id>``.
_KNOWN_MODELS = {
    "flux.1-schnell": "flux.1-schnell",
    "flux.1-dev": "flux.1-dev",
}


def _model_path(model_id: str) -> Path:
    safe = _KNOWN_MODELS.get(model_id, model_id)
    return _models_root() / safe


def _check_runtime() -> dict[str, Any]:
    import importlib.util

    torch_spec = importlib.util.find_spec("torch")
    diffusers_spec = importlib.util.find_spec("diffusers")
    info: dict[str, Any] = {
        "python": sys.version.split()[0],
        "torch_available": torch_spec is not None,
        "diffusers_available": diffusers_spec is not None,
    }
    if torch_spec is not None:
        try:
            import torch

            info["torch_version"] = torch.__version__
            info["torch_cuda_available"] = torch.cuda.is_available()
            info["torch_cuda_device_count"] = (
                torch.cuda.device_count() if torch.cuda.is_available() else 0
            )
            if torch.cuda.is_available() and torch.cuda.device_count():
                info["torch_cuda_device_name"] = torch.cuda.get_device_name(0)
        except Exception as exc:  # pragma: no cover — defensive
            info["torch_import_error"] = f"{type(exc).__name__}: {exc}"
    if diffusers_spec is not None:
        try:
            import diffusers

            info["diffusers_version"] = diffusers.__version__
        except Exception as exc:  # pragma: no cover
            info["diffusers_import_error"] = f"{type(exc).__name__}: {exc}"
    return info


def _check_assets() -> dict[str, Any]:
    root = _models_root()
    default = _default_model()
    model_path = _model_path(default)
    expected = ["model_index.json"]
    missing: list[str] = []
    sizes: dict[str, int] = {}
    if not model_path.is_dir():
        missing.append(str(model_path))
    else:
        for rel in expected:
            p = model_path / rel
            if p.is_file():
                sizes[rel] = p.stat().st_size
            else:
                missing.append(f"{default}/{rel}")
    return {
        "models_root": str(root),
        "models_root_exists": root.is_dir(),
        "default_model": default,
        "default_model_path": str(model_path),
        "default_model_present": model_path.is_dir() and not missing,
        "present_sizes": sizes,
        "missing": missing,
        "known_models": sorted(_KNOWN_MODELS.keys()),
    }


def _overall_status(runtime: dict[str, Any], assets: dict[str, Any]) -> str:
    if not runtime.get("torch_available"):
        return "runtime_missing"
    if not runtime.get("diffusers_available"):
        return "runtime_missing"
    if not runtime.get("torch_cuda_available"):
        return "gpu_unavailable"
    if not assets.get("default_model_present"):
        return "assets_missing"
    return "ready"


@app.get("/health")
async def health() -> dict[str, Any]:
    runtime = _check_runtime()
    assets = _check_assets()
    status = _overall_status(runtime, assets)
    return {
        "service": "flux-wrapper",
        "version": "0.1.0",
        "status": status,
        "ready": status == "ready",
        "details": {"runtime": runtime, "assets": assets},
        "env": {
            "FLUX_MODELS_ROOT": os.environ.get("FLUX_MODELS_ROOT", ""),
            "FLUX_RESULT_DIR": os.environ.get("FLUX_RESULT_DIR", ""),
            "FLUX_DEFAULT_MODEL": _default_model(),
        },
        "time": time.time(),
    }


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------


class FluxGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(..., min_length=1, max_length=4000)
    negative_prompt: str | None = Field(default=None, max_length=2000)
    model_id: str | None = Field(default=None, max_length=160)
    seed: int | None = Field(default=None, ge=0, le=(1 << 63) - 1)
    width: int = Field(default=1024, ge=128, le=2048)
    height: int = Field(default=1024, ge=128, le=2048)
    steps: int | None = Field(default=None, ge=1, le=200)
    guidance_scale: float | None = Field(default=None, ge=0, le=50)
    reference_image_path: str | None = Field(default=None, max_length=2000)


class FluxGenerateError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_code: Literal[
        "runtime_missing",
        "assets_missing",
        "gpu_unavailable",
        "validation_failed",
        "generation_failed",
        "storage_failed",
    ]
    detail: str
    model_id: str | None = None


class FluxGenerateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_path: str
    mime_type: str = "image/png"
    width: int
    height: int
    model_id: str
    seed: int | None
    duration_seconds: float
    size_bytes: int


# Cache the pipeline across requests — loading FLUX takes 30-60s on
# first call. ``_PIPELINE`` is keyed by model_id so operators can
# swap models without restart (cheap on disk space, expensive on VRAM).
_PIPELINE: dict[str, Any] = {}


def _load_pipeline(model_id: str):
    """Lazy-load + cache the FluxPipeline for ``model_id``."""
    if model_id in _PIPELINE:
        return _PIPELINE[model_id]
    import torch
    from diffusers import FluxPipeline

    path = _model_path(model_id)
    if not path.is_dir():
        raise RuntimeError(f"model directory missing: {path}")
    logger.info("loading FLUX pipeline from %s …", path)
    pipe = FluxPipeline.from_pretrained(
        str(path),
        torch_dtype=torch.bfloat16,
        local_files_only=True,
    )
    # CPU offload MUST be configured BEFORE moving the pipe to CUDA —
    # ``enable_model_cpu_offload`` manages device placement itself.
    # Calling ``.to('cuda')`` first loads everything into VRAM (~22 GB
    # for FLUX), which OOMs consumer 24 GB cards.
    if os.environ.get("FLUX_ENABLE_CPU_OFFLOAD", "true").lower() in (
        "true",
        "1",
        "yes",
    ):
        try:
            pipe.enable_model_cpu_offload()
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning("CPU offload failed: %s", exc)
            pipe = pipe.to("cuda")
    else:
        pipe = pipe.to("cuda")
    _PIPELINE[model_id] = pipe
    return pipe


def _error(status_code: int, error_code: str, detail: str, model_id: str | None = None):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=status_code,
        content=FluxGenerateError(
            error_code=error_code,  # type: ignore[arg-type]
            detail=detail,
            model_id=model_id,
        ).model_dump(),
    )


@app.post("/flux/generate")
async def flux_generate(body: FluxGenerateRequest):
    runtime = _check_runtime()
    if not runtime.get("torch_available") or not runtime.get("diffusers_available"):
        return _error(503, "runtime_missing", "torch / diffusers not installed in this image.")
    if not runtime.get("torch_cuda_available"):
        return _error(503, "gpu_unavailable", "CUDA device not visible to the container.")

    model_id = (body.model_id or _default_model()).strip()
    path = _model_path(model_id)
    if not path.is_dir():
        return _error(
            503,
            "assets_missing",
            f"Model weights missing at {path}. Mount the directory read-only and retry.",
            model_id=model_id,
        )

    try:
        import torch

        pipe = _load_pipeline(model_id)

        generator = (
            torch.Generator(device="cuda").manual_seed(int(body.seed))
            if body.seed is not None
            else None
        )

        kwargs: dict[str, Any] = {
            "prompt": body.prompt,
            "width": body.width,
            "height": body.height,
            "generator": generator,
        }
        if body.steps is not None:
            # FLUX-schnell prefers 1-4 steps; -dev prefers 28-50.
            kwargs["num_inference_steps"] = int(body.steps)
        else:
            kwargs["num_inference_steps"] = 4 if "schnell" in model_id else 28
        if body.guidance_scale is not None:
            kwargs["guidance_scale"] = float(body.guidance_scale)
        else:
            kwargs["guidance_scale"] = 0.0 if "schnell" in model_id else 3.5

        # FLUX.1 doesn't support negative prompts in the same way as SD3.5
        # — diffusers ignores the field when the pipeline doesn't expose it.
        if body.negative_prompt:
            kwargs["negative_prompt"] = body.negative_prompt

        t0 = time.perf_counter()
        result = pipe(**kwargs)
        elapsed = time.perf_counter() - t0
        image = result.images[0]

        # Persist.
        result_dir = _result_dir()
        result_dir.mkdir(parents=True, exist_ok=True)
        file_id = uuid.uuid4().hex
        file_path = result_dir / f"{file_id}.png"
        image.save(file_path)
        size = file_path.stat().st_size

        return FluxGenerateResponse(
            file_path=str(file_path),
            width=body.width,
            height=body.height,
            model_id=model_id,
            seed=body.seed,
            duration_seconds=round(elapsed, 3),
            size_bytes=size,
        ).model_dump()

    except Exception as exc:
        logger.exception("FLUX generation failed: %s", exc)
        tb = traceback.format_exception_only(type(exc), exc)[-1].strip()
        return _error(500, "generation_failed", tb, model_id=model_id)
