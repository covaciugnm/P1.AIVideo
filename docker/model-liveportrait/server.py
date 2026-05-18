"""LivePortrait GPU HTTP wrapper — Phase 12Y."""
from __future__ import annotations
import logging, os, subprocess, sys, time, traceback
from pathlib import Path
from typing import Any, Literal
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)
app = FastAPI(title="LivePortrait GPU wrapper", version="0.1.0")


def _models_root() -> Path:
    return Path(os.environ.get("LIVEPORTRAIT_MODELS_ROOT", "/models/lipsync/liveportrait"))


def _source_dir() -> Path:
    return Path(os.environ.get("LIVEPORTRAIT_SOURCE_DIR", "/opt/liveportrait-src"))


def _result_dir() -> Path:
    return Path(os.environ.get("LIVEPORTRAIT_RESULT_DIR", "/storage/artifacts/liveportrait"))


# LivePortrait expects a tree under liveportrait/ with appearance_feature_extractor,
# motion_extractor, warping_module, spade_generator, etc.
_REQUIRED_WEIGHTS = (
    "liveportrait/base_models/appearance_feature_extractor.pth",
    "liveportrait/base_models/motion_extractor.pth",
    "liveportrait/base_models/warping_module.pth",
    "liveportrait/base_models/spade_generator.pth",
    "liveportrait/base_models/stitching_retargeting_module.pth",
)


def _check_runtime() -> dict[str, Any]:
    import importlib.util
    info = {
        "python": sys.version.split()[0],
        "torch_available": importlib.util.find_spec("torch") is not None,
        "cv2_available": importlib.util.find_spec("cv2") is not None,
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
        except Exception as exc:
            info["torch_import_error"] = f"{type(exc).__name__}: {exc}"
    return info


def _check_assets() -> dict[str, Any]:
    root = _models_root()
    missing = []
    sizes = {}
    for rel in _REQUIRED_WEIGHTS:
        p = root / rel
        if p.is_file():
            sizes[rel] = p.stat().st_size
        else:
            missing.append(rel)
    return {
        "models_root": str(root),
        "models_root_exists": root.is_dir(),
        "present_sizes": sizes,
        "missing": missing,
        "required": list(_REQUIRED_WEIGHTS),
    }


def _overall_status(runtime, assets):
    if not runtime.get("torch_available") or not runtime.get("cv2_available"):
        return "runtime_missing"
    if not runtime.get("torch_cuda_available"):
        return "gpu_unavailable"
    if not runtime.get("inference_script_exists"):
        return "runtime_missing"
    if assets.get("missing"):
        return "assets_missing"
    return "ready"


@app.get("/health")
async def health() -> dict[str, Any]:
    runtime = _check_runtime()
    assets = _check_assets()
    status = _overall_status(runtime, assets)
    return {
        "service": "liveportrait-wrapper",
        "version": "0.1.0",
        "status": status,
        "ready": status == "ready",
        "details": {"runtime": runtime, "assets": assets},
        "env": {"LIVEPORTRAIT_MODELS_ROOT": str(_models_root())},
        "time": time.time(),
    }


class LivePortraitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_image_path: str = Field(..., max_length=2000)
    driving_video_path: str = Field(..., max_length=2000)
    output_path: str = Field(..., max_length=2000)
    flag_relative: bool = True
    flag_do_crop: bool = True
    flag_stitching: bool = True


class LivePortraitError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error_code: Literal["runtime_missing", "assets_missing", "gpu_unavailable",
                        "generation_failed", "storage_failed"]
    detail: str


def _err(code, ec, detail):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=code,
                        content=LivePortraitError(error_code=ec,  # type: ignore[arg-type]
                                                  detail=detail).model_dump())


@app.post("/liveportrait/generate")
async def generate(body: LivePortraitRequest):
    runtime = _check_runtime()
    assets = _check_assets()
    status = _overall_status(runtime, assets)
    if status == "runtime_missing":
        return _err(503, "runtime_missing", "torch/cv2 or inference.py missing.")
    if status == "gpu_unavailable":
        return _err(503, "gpu_unavailable", "CUDA not visible.")
    if status == "assets_missing":
        return _err(503, "assets_missing",
                    f"LivePortrait weights missing: {assets['missing']}")

    out_path = Path(body.output_path)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _err(500, "storage_failed", str(exc))

    cmd = [
        sys.executable, str(_source_dir() / "inference.py"),
        "-s", body.source_image_path,
        "-d", body.driving_video_path,
        "-o", str(out_path.parent),
    ]
    if not body.flag_relative:
        cmd.append("--no_flag_relative")
    if not body.flag_do_crop:
        cmd.append("--no_flag_do_crop")
    if not body.flag_stitching:
        cmd.append("--no_flag_stitching")

    t0 = time.perf_counter()
    try:
        proc = subprocess.run(cmd, cwd=str(_source_dir()),
                              capture_output=True, text=True,
                              timeout=int(os.environ.get("LIVEPORTRAIT_INFER_TIMEOUT", "900")))
        elapsed = time.perf_counter() - t0
        if proc.returncode != 0:
            return _err(500, "generation_failed",
                        f"inference exit={proc.returncode}: {proc.stderr[-300:]}")
        candidates = sorted(out_path.parent.glob("*.mp4"),
                            key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            return _err(500, "generation_failed", "no MP4 produced")
        produced = candidates[0]
        if produced != out_path:
            produced.rename(out_path)
        return {
            "status": "completed",
            "output_path": str(out_path),
            "size_bytes": out_path.stat().st_size,
            "duration_seconds": elapsed,
        }
    except subprocess.TimeoutExpired:
        return _err(500, "generation_failed", "inference timeout")
    except Exception as exc:
        tb = traceback.format_exception_only(type(exc), exc)[-1].strip()
        return _err(500, "generation_failed", tb)
