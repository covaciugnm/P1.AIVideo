"""Wav2Lip GPU HTTP wrapper — Phase 12Y.

Calls the upstream Rudrabha/Wav2Lip inference script via subprocess.
Operator places model weights at ``${WAV2LIP_CHECKPOINTS_DIR}``:
  - wav2lip_gan.pth (preferred — sharper)
  - wav2lip.pth (faster, less sharp)
"""
from __future__ import annotations

import logging
import os
import shlex
import subprocess
import sys
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)
app = FastAPI(title="Wav2Lip GPU wrapper", version="0.1.0")


def _models_root() -> Path:
    return Path(os.environ.get("WAV2LIP_CHECKPOINTS_DIR", "/models/lipsync/wav2lip"))


def _source_dir() -> Path:
    return Path(os.environ.get("WAV2LIP_SOURCE_DIR", "/opt/wav2lip-src"))


def _result_dir() -> Path:
    return Path(os.environ.get("WAV2LIP_RESULT_DIR", "/storage/artifacts/wav2lip"))


def _check_runtime() -> dict[str, Any]:
    import importlib.util

    info = {
        "python": sys.version.split()[0],
        "torch_available": importlib.util.find_spec("torch") is not None,
        "cv2_available": importlib.util.find_spec("cv2") is not None,
        "librosa_available": importlib.util.find_spec("librosa") is not None,
        "source_dir": str(_source_dir()),
        "source_dir_exists": _source_dir().is_dir(),
        "inference_script_exists": (_source_dir() / "inference.py").is_file(),
    }
    if info["torch_available"]:
        try:
            import torch
            info["torch_version"] = torch.__version__
            info["torch_cuda_available"] = torch.cuda.is_available()
            if torch.cuda.is_available():
                info["torch_cuda_device_name"] = torch.cuda.get_device_name(0)
        except Exception as exc:  # pragma: no cover
            info["torch_import_error"] = f"{type(exc).__name__}: {exc}"
    return info


def _check_assets() -> dict[str, Any]:
    root = _models_root()
    sharp = root / "wav2lip_gan.pth"
    fast = root / "wav2lip.pth"
    return {
        "models_root": str(root),
        "models_root_exists": root.is_dir(),
        "wav2lip_gan_present": sharp.is_file(),
        "wav2lip_gan_size_bytes": sharp.stat().st_size if sharp.is_file() else 0,
        "wav2lip_present": fast.is_file(),
        "any_checkpoint_present": sharp.is_file() or fast.is_file(),
    }


def _overall_status(runtime: dict, assets: dict) -> str:
    if not runtime.get("torch_available") or not runtime.get("cv2_available"):
        return "runtime_missing"
    if not runtime.get("torch_cuda_available"):
        return "gpu_unavailable"
    if not runtime.get("inference_script_exists"):
        return "runtime_missing"
    if not assets.get("any_checkpoint_present"):
        return "assets_missing"
    return "ready"


@app.get("/health")
async def health() -> dict[str, Any]:
    runtime = _check_runtime()
    assets = _check_assets()
    status = _overall_status(runtime, assets)
    return {
        "service": "wav2lip-wrapper",
        "version": "0.1.0",
        "status": status,
        "ready": status == "ready",
        "details": {"runtime": runtime, "assets": assets},
        "env": {
            "WAV2LIP_CHECKPOINTS_DIR": str(_models_root()),
            "WAV2LIP_SOURCE_DIR": str(_source_dir()),
        },
        "time": time.time(),
    }


class Wav2LipGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_path: str = Field(..., max_length=2000)
    audio_path: str = Field(..., max_length=2000)
    output_path: str = Field(..., max_length=2000)
    checkpoint: Literal["wav2lip_gan", "wav2lip"] = "wav2lip_gan"
    pads: list[int] = Field(default_factory=lambda: [0, 10, 0, 0])
    resize_factor: int = Field(default=1, ge=1, le=8)
    nosmooth: bool = False
    static: bool = False


class Wav2LipError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_code: Literal["runtime_missing", "assets_missing", "gpu_unavailable",
                        "generation_failed", "storage_failed"]
    detail: str


def _err(code: int, error_code: str, detail: str):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=code,
                        content=Wav2LipError(error_code=error_code,  # type: ignore[arg-type]
                                              detail=detail).model_dump())


@app.post("/wav2lip/generate")
async def generate(body: Wav2LipGenerateRequest):
    runtime = _check_runtime()
    assets = _check_assets()
    status = _overall_status(runtime, assets)
    if status == "runtime_missing":
        return _err(503, "runtime_missing", "torch/cv2/librosa or inference.py missing in image.")
    if status == "gpu_unavailable":
        return _err(503, "gpu_unavailable", "CUDA device not visible.")
    if status == "assets_missing":
        return _err(503, "assets_missing",
                    f"Wav2Lip checkpoint (wav2lip_gan.pth or wav2lip.pth) missing under {_models_root()}.")

    ckpt = _models_root() / f"{body.checkpoint}.pth"
    if not ckpt.is_file():
        return _err(503, "assets_missing", f"Checkpoint {ckpt} not found.")

    result_dir = _result_dir()
    try:
        result_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _err(500, "storage_failed", str(exc))

    out_path = Path(body.output_path)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _err(500, "storage_failed", str(exc))

    cmd = [
        sys.executable, str(_source_dir() / "inference.py"),
        "--checkpoint_path", str(ckpt),
        "--face", body.image_path,
        "--audio", body.audio_path,
        "--outfile", str(out_path),
        "--resize_factor", str(body.resize_factor),
        "--pads", *[str(p) for p in body.pads],
    ]
    if body.nosmooth:
        cmd.append("--nosmooth")
    if body.static:
        cmd.append("--static")

    t0 = time.perf_counter()
    try:
        proc = subprocess.run(cmd, cwd=str(_source_dir()),
                              capture_output=True, text=True,
                              timeout=int(os.environ.get("WAV2LIP_INFER_TIMEOUT", "600")))
        elapsed = time.perf_counter() - t0
        if proc.returncode != 0:
            logger.warning("wav2lip failed: %s", proc.stderr[-500:])
            return _err(500, "generation_failed",
                        f"inference.py exit={proc.returncode}: {proc.stderr[-300:]}")
        size = out_path.stat().st_size if out_path.is_file() else 0
        return {
            "status": "completed",
            "output_path": str(out_path),
            "size_bytes": size,
            "duration_seconds": elapsed,
            "checkpoint": body.checkpoint,
        }
    except subprocess.TimeoutExpired:
        return _err(500, "generation_failed", "inference timeout")
    except Exception as exc:
        tb = traceback.format_exception_only(type(exc), exc)[-1].strip()
        return _err(500, "generation_failed", tb)
