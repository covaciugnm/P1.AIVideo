"""Mochi-1 HTTP wrapper. Text → MP4 (Genmo SOTA, 4-bit option)."""
from __future__ import annotations
import logging, os, sys, time, traceback
from pathlib import Path
from typing import Any, Literal
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)
app = FastAPI(title="Mochi-1 GPU wrapper", version="0.1.0")


def _models_root() -> Path:
    return Path(os.environ.get("MOCHI_MODELS_ROOT", "/models/video/mochi"))


def _result_dir() -> Path:
    return Path(os.environ.get("MOCHI_RESULT_DIR", "/storage/artifacts/mochi"))


def _check_runtime() -> dict[str, Any]:
    import importlib.util
    info = {"python": sys.version.split()[0],
            "torch_available": importlib.util.find_spec("torch") is not None,
            "diffusers_available": importlib.util.find_spec("diffusers") is not None,
            "bitsandbytes_available": importlib.util.find_spec("bitsandbytes") is not None}
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
    return {"service": "mochi-wrapper", "version": "0.1.0", "status": st,
            "ready": st == "ready",
            "details": {"runtime": rt, "assets": a},
            "env": {"MOCHI_QUANTIZE": os.environ.get("MOCHI_QUANTIZE", "")},
            "time": time.time()}


class MochiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(..., min_length=1, max_length=4000)
    negative_prompt: str | None = Field(default=None, max_length=2000)
    output_path: str = Field(..., max_length=2000)
    num_frames: int = Field(default=84, ge=9, le=164)
    fps: int = Field(default=30, ge=1, le=60)
    width: int = Field(default=848, ge=256, le=1280)
    height: int = Field(default=480, ge=256, le=1280)
    steps: int = Field(default=64, ge=1, le=200)
    guidance_scale: float = Field(default=4.5, ge=0.0, le=50.0)
    seed: int | None = None


class MochiError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error_code: Literal["runtime_missing", "assets_missing", "gpu_unavailable",
                        "generation_failed", "storage_failed"]
    detail: str


def _err(c, ec, d):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=c,
                        content=MochiError(error_code=ec, detail=d).model_dump())  # type: ignore[arg-type]


_PIPE = None


def _load():
    global _PIPE
    if _PIPE is not None:
        return _PIPE
    import torch
    from diffusers import MochiPipeline, MochiTransformer3DModel
    quantize = os.environ.get("MOCHI_QUANTIZE", "").lower()
    if quantize in ("int4", "nf4", "4bit"):
        from transformers import BitsAndBytesConfig
        bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16,
                                  bnb_4bit_quant_type="nf4")
        transformer = MochiTransformer3DModel.from_pretrained(
            str(_models_root()), subfolder="transformer",
            torch_dtype=torch.bfloat16, quantization_config=bnb,
            local_files_only=True)
        _PIPE = MochiPipeline.from_pretrained(
            str(_models_root()), transformer=transformer,
            torch_dtype=torch.bfloat16, local_files_only=True)
    else:
        _PIPE = MochiPipeline.from_pretrained(str(_models_root()),
                                                torch_dtype=torch.bfloat16,
                                                local_files_only=True)
    _PIPE.enable_model_cpu_offload()
    _PIPE.enable_vae_tiling()
    return _PIPE


@app.post("/mochi/generate")
async def generate(body: MochiRequest):
    rt = _check_runtime(); a = _check_assets()
    st = _overall_status(rt, a)
    if st == "runtime_missing":
        return _err(503, "runtime_missing", "torch/diffusers missing")
    if st == "gpu_unavailable":
        return _err(503, "gpu_unavailable", "CUDA not visible")
    if st == "assets_missing":
        return _err(503, "assets_missing", f"Mochi model missing at {_models_root()}")
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
        result = pipe(prompt=body.prompt, negative_prompt=body.negative_prompt or "",
                       num_frames=body.num_frames, num_inference_steps=body.steps,
                       guidance_scale=body.guidance_scale,
                       width=body.width, height=body.height, generator=gen)
        frames = result.frames[0]
        elapsed = time.perf_counter() - t0
        imageio.mimsave(str(out), [f.convert("RGB") for f in frames], fps=body.fps,
                         codec="libx264", output_params=["-pix_fmt", "yuv420p"])
        return {"status": "completed", "output_path": str(out),
                "size_bytes": out.stat().st_size, "duration_seconds": elapsed,
                "num_frames": body.num_frames, "fps": body.fps,
                "quantize": os.environ.get("MOCHI_QUANTIZE", "bf16")}
    except Exception as exc:
        logger.exception("Mochi failed")
        tb = traceback.format_exception_only(type(exc), exc)[-1].strip()
        return _err(500, "generation_failed", tb)
