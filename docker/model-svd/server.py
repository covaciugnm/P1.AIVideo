"""Stable Video Diffusion HTTP wrapper. img → MP4."""
from __future__ import annotations
import logging, os, sys, time, traceback, uuid
from pathlib import Path
from typing import Any, Literal
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)
app = FastAPI(title="SVD GPU wrapper", version="0.1.0")


def _models_root() -> Path:
    return Path(os.environ.get("SVD_MODELS_ROOT", "/models/video/svd"))


def _result_dir() -> Path:
    return Path(os.environ.get("SVD_RESULT_DIR", "/storage/artifacts/svd"))


def _check_runtime() -> dict[str, Any]:
    import importlib.util
    info = {"python": sys.version.split()[0],
            "torch_available": importlib.util.find_spec("torch") is not None,
            "diffusers_available": importlib.util.find_spec("diffusers") is not None}
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
    return {"models_root": str(root), "models_root_exists": root.is_dir(),
            "model_index_present": (root / "model_index.json").is_file()}


def _overall_status(rt, a):
    if not rt.get("torch_available") or not rt.get("diffusers_available"):
        return "runtime_missing"
    if not rt.get("torch_cuda_available"):
        return "gpu_unavailable"
    if not a.get("model_index_present"):
        return "assets_missing"
    return "ready"


@app.get("/health")
async def health() -> dict[str, Any]:
    rt = _check_runtime(); a = _check_assets()
    st = _overall_status(rt, a)
    return {"service": "svd-wrapper", "version": "0.1.0", "status": st,
            "ready": st == "ready",
            "details": {"runtime": rt, "assets": a}, "time": time.time()}


class SvdRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    image_path: str = Field(..., max_length=2000)
    output_path: str = Field(..., max_length=2000)
    num_frames: int = Field(default=25, ge=2, le=120)
    fps: int = Field(default=7, ge=1, le=60)
    motion_bucket_id: int = Field(default=127, ge=1, le=255)
    noise_aug_strength: float = Field(default=0.02, ge=0.0, le=1.0)
    seed: int | None = None
    decode_chunk_size: int = Field(default=8, ge=1, le=64)


class SvdError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error_code: Literal["runtime_missing", "assets_missing", "gpu_unavailable",
                        "generation_failed", "storage_failed"]
    detail: str


def _err(c, ec, d):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=c,
                        content=SvdError(error_code=ec, detail=d).model_dump())  # type: ignore[arg-type]


_PIPE = None


def _load():
    global _PIPE
    if _PIPE is not None:
        return _PIPE
    import torch
    from diffusers import StableVideoDiffusionPipeline
    _PIPE = StableVideoDiffusionPipeline.from_pretrained(
        str(_models_root()), torch_dtype=torch.float16, local_files_only=True,
        variant="fp16")
    _PIPE.enable_model_cpu_offload()
    return _PIPE


@app.post("/svd/generate")
async def generate(body: SvdRequest):
    rt = _check_runtime(); a = _check_assets()
    st = _overall_status(rt, a)
    if st == "runtime_missing":
        return _err(503, "runtime_missing", "torch/diffusers missing")
    if st == "gpu_unavailable":
        return _err(503, "gpu_unavailable", "CUDA not visible")
    if st == "assets_missing":
        return _err(503, "assets_missing", f"SVD model missing at {_models_root()}")
    out = Path(body.output_path)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _err(500, "storage_failed", str(exc))
    try:
        import torch
        from PIL import Image
        import imageio
        pipe = _load()
        image = Image.open(body.image_path).convert("RGB")
        # SVD expects 1024×576 or 576×1024.
        image = image.resize((1024, 576))
        gen = torch.Generator(device="cpu").manual_seed(int(body.seed)) if body.seed is not None else None
        t0 = time.perf_counter()
        result = pipe(image, num_frames=body.num_frames,
                       motion_bucket_id=body.motion_bucket_id,
                       noise_aug_strength=body.noise_aug_strength,
                       decode_chunk_size=body.decode_chunk_size,
                       generator=gen)
        frames = result.frames[0]
        elapsed = time.perf_counter() - t0
        # imageio writes MP4 with H.264.
        imageio.mimsave(str(out), [f.convert("RGB") for f in frames], fps=body.fps,
                         codec="libx264", output_params=["-pix_fmt", "yuv420p"])
        return {"status": "completed", "output_path": str(out),
                "size_bytes": out.stat().st_size, "duration_seconds": elapsed,
                "num_frames": body.num_frames, "fps": body.fps}
    except Exception as exc:
        logger.exception("SVD failed")
        tb = traceback.format_exception_only(type(exc), exc)[-1].strip()
        return _err(500, "generation_failed", tb)
