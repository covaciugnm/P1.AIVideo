"""LTX-Video HTTP wrapper. Text → MP4 (real-time DiT model)."""
from __future__ import annotations
import logging, os, sys, time, traceback
from pathlib import Path
from typing import Any, Literal
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)
app = FastAPI(title="LTX-Video GPU wrapper", version="0.1.0")


def _models_root() -> Path:
    return Path(os.environ.get("LTX_MODELS_ROOT", "/models/video/ltx"))


def _result_dir() -> Path:
    return Path(os.environ.get("LTX_RESULT_DIR", "/storage/artifacts/ltx"))


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
    return {"service": "ltx-wrapper", "version": "0.1.0", "status": st,
            "ready": st == "ready",
            "details": {"runtime": rt, "assets": a}, "time": time.time()}


class LtxRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(..., min_length=1, max_length=4000)
    negative_prompt: str | None = Field(default=None, max_length=2000)
    output_path: str = Field(..., max_length=2000)
    num_frames: int = Field(default=121, ge=9, le=257)
    fps: int = Field(default=24, ge=1, le=60)
    width: int = Field(default=704, ge=256, le=1024)
    height: int = Field(default=480, ge=256, le=1024)
    steps: int = Field(default=40, ge=1, le=200)
    guidance_scale: float = Field(default=3.0, ge=0.0, le=50.0)
    seed: int | None = None


class LtxError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error_code: Literal["runtime_missing", "assets_missing", "gpu_unavailable",
                        "generation_failed", "storage_failed"]
    detail: str


def _err(c, ec, d):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=c,
                        content=LtxError(error_code=ec, detail=d).model_dump())  # type: ignore[arg-type]


_PIPE = None


def _load():
    global _PIPE
    if _PIPE is not None:
        return _PIPE
    import torch
    from diffusers import LTXPipeline
    _PIPE = LTXPipeline.from_pretrained(str(_models_root()),
                                          torch_dtype=torch.bfloat16,
                                          local_files_only=True)
    _PIPE.enable_model_cpu_offload()
    return _PIPE


@app.post("/ltx/generate")
async def generate(body: LtxRequest):
    rt = _check_runtime(); a = _check_assets()
    st = _overall_status(rt, a)
    if st == "runtime_missing":
        return _err(503, "runtime_missing", "torch/diffusers missing")
    if st == "gpu_unavailable":
        return _err(503, "gpu_unavailable", "CUDA not visible")
    if st == "assets_missing":
        return _err(503, "assets_missing", f"LTX model missing at {_models_root()}")
    out = Path(body.output_path)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _err(500, "storage_failed", str(exc))
    try:
        import torch, imageio
        pipe = _load()
        gen = torch.Generator(device="cpu").manual_seed(int(body.seed)) if body.seed is not None else None
        t0 = time.perf_counter()
        result = pipe(prompt=body.prompt, negative_prompt=body.negative_prompt or "worst quality, blurry",
                       num_frames=body.num_frames, num_inference_steps=body.steps,
                       guidance_scale=body.guidance_scale,
                       width=body.width, height=body.height, generator=gen)
        frames = result.frames[0]
        elapsed = time.perf_counter() - t0
        imageio.mimsave(str(out), [f.convert("RGB") for f in frames], fps=body.fps,
                         codec="libx264", output_params=["-pix_fmt", "yuv420p"])
        return {"status": "completed", "output_path": str(out),
                "size_bytes": out.stat().st_size, "duration_seconds": elapsed,
                "num_frames": body.num_frames, "fps": body.fps}
    except Exception as exc:
        logger.exception("LTX failed")
        tb = traceback.format_exception_only(type(exc), exc)[-1].strip()
        return _err(500, "generation_failed", tb)
