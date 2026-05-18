"""Stable Diffusion XL GPU HTTP wrapper — Phase 12W.

Same pattern as docker/model-flux/server.py but uses
``diffusers.StableDiffusionXLPipeline``. Operator places SDXL
checkpoint files under ``${SDXL_MODELS_ROOT}/<model_id>``.
"""
from __future__ import annotations

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

app = FastAPI(title="SDXL GPU wrapper", version="0.1.0")


def _models_root() -> Path:
    return Path(os.environ.get("SDXL_MODELS_ROOT", "/models/image/sdxl"))


def _result_dir() -> Path:
    return Path(os.environ.get("SDXL_RESULT_DIR", "/storage/artifacts/sdxl"))


def _default_model() -> str:
    return os.environ.get("SDXL_DEFAULT_MODEL", "sdxl-base-1.0").strip()


_KNOWN_MODELS = {
    "sdxl-base-1.0": "sdxl-base-1.0",
    "sdxl-turbo": "sdxl-turbo",
    "sdxl-lightning": "sdxl-lightning",
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
            if torch.cuda.is_available() and torch.cuda.device_count():
                info["torch_cuda_device_name"] = torch.cuda.get_device_name(0)
        except Exception as exc:  # pragma: no cover
            info["torch_import_error"] = f"{type(exc).__name__}: {exc}"
    return info


def _check_assets() -> dict[str, Any]:
    root = _models_root()
    default = _default_model()
    path = _model_path(default)
    return {
        "models_root": str(root),
        "models_root_exists": root.is_dir(),
        "default_model": default,
        "default_model_path": str(path),
        "default_model_present": path.is_dir() and (path / "model_index.json").is_file(),
        "known_models": sorted(_KNOWN_MODELS.keys()),
    }


def _overall_status(runtime: dict, assets: dict) -> str:
    if not runtime.get("torch_available") or not runtime.get("diffusers_available"):
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
        "service": "sdxl-wrapper",
        "version": "0.1.0",
        "status": status,
        "ready": status == "ready",
        "details": {"runtime": runtime, "assets": assets},
        "env": {
            "SDXL_MODELS_ROOT": os.environ.get("SDXL_MODELS_ROOT", ""),
            "SDXL_DEFAULT_MODEL": _default_model(),
        },
        "time": time.time(),
    }


class SdxlGenerateRequest(BaseModel):
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


class SdxlGenerateError(BaseModel):
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


_PIPELINE: dict[str, Any] = {}


def _load_pipeline(model_id: str):
    if model_id in _PIPELINE:
        return _PIPELINE[model_id]
    import torch
    from diffusers import StableDiffusionXLPipeline

    path = _model_path(model_id)
    if not path.is_dir():
        raise RuntimeError(f"model directory missing: {path}")
    logger.info("loading SDXL pipeline from %s …", path)
    pipe = StableDiffusionXLPipeline.from_pretrained(
        str(path),
        torch_dtype=torch.float16,
        use_safetensors=True,
        local_files_only=True,
        variant="fp16",
    )
    pipe = pipe.to("cuda")
    _PIPELINE[model_id] = pipe
    return pipe


def _error(status_code: int, error_code: str, detail: str, model_id: str | None = None):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=status_code,
        content=SdxlGenerateError(
            error_code=error_code,  # type: ignore[arg-type]
            detail=detail,
            model_id=model_id,
        ).model_dump(),
    )


@app.post("/sdxl/generate")
async def sdxl_generate(body: SdxlGenerateRequest):
    runtime = _check_runtime()
    if not runtime.get("torch_available") or not runtime.get("diffusers_available"):
        return _error(503, "runtime_missing", "torch / diffusers not installed.")
    if not runtime.get("torch_cuda_available"):
        return _error(503, "gpu_unavailable", "CUDA not visible.")

    model_id = (body.model_id or _default_model()).strip()
    path = _model_path(model_id)
    if not path.is_dir():
        return _error(503, "assets_missing", f"Weights missing at {path}.", model_id=model_id)

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
            "num_inference_steps": int(body.steps) if body.steps else 30,
            "guidance_scale": float(body.guidance_scale) if body.guidance_scale else 7.5,
        }
        if body.negative_prompt:
            kwargs["negative_prompt"] = body.negative_prompt

        t0 = time.perf_counter()
        image = pipe(**kwargs).images[0]
        elapsed = time.perf_counter() - t0

        result_dir = _result_dir()
        result_dir.mkdir(parents=True, exist_ok=True)
        file_path = result_dir / f"{uuid.uuid4().hex}.png"
        image.save(file_path)
        size = file_path.stat().st_size

        return {
            "file_path": str(file_path),
            "mime_type": "image/png",
            "width": body.width,
            "height": body.height,
            "model_id": model_id,
            "seed": body.seed,
            "duration_seconds": round(elapsed, 3),
            "size_bytes": size,
        }
    except Exception as exc:
        logger.exception("SDXL generation failed: %s", exc)
        tb = traceback.format_exception_only(type(exc), exc)[-1].strip()
        return _error(500, "generation_failed", tb, model_id=model_id)
