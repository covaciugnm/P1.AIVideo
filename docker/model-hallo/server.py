"""Hallo2 HTTP wrapper (HD talking head, audio-driven)."""
from __future__ import annotations
import logging, os, subprocess, sys, time, traceback
from pathlib import Path
from typing import Any, Literal
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)
app = FastAPI(title="Hallo2 GPU wrapper", version="0.1.0")


def _models_root() -> Path:
    return Path(os.environ.get("HALLO_MODELS_ROOT", "/models/lipsync/hallo"))


def _source_dir() -> Path:
    return Path(os.environ.get("HALLO_SOURCE_DIR", "/opt/hallo-src"))


def _result_dir() -> Path:
    return Path(os.environ.get("HALLO_RESULT_DIR", "/storage/artifacts/hallo"))


def _check_runtime() -> dict[str, Any]:
    import importlib.util
    info = {"python": sys.version.split()[0],
            "torch_available": importlib.util.find_spec("torch") is not None,
            "diffusers_available": importlib.util.find_spec("diffusers") is not None,
            "source_dir": str(_source_dir()),
            "source_dir_exists": _source_dir().is_dir()}
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
            "has_any_pth": any(root.rglob("*.pth")) if root.is_dir() else False,
            "has_any_safetensors": any(root.rglob("*.safetensors")) if root.is_dir() else False}


def _overall_status(rt, a):
    if not rt.get("torch_available") or not rt.get("diffusers_available"):
        return "runtime_missing"
    if not rt.get("torch_cuda_available"):
        return "gpu_unavailable"
    if not (a.get("has_any_pth") or a.get("has_any_safetensors")):
        return "assets_missing"
    return "ready"


@app.get("/health")
async def health() -> dict[str, Any]:
    rt = _check_runtime(); a = _check_assets()
    st = _overall_status(rt, a)
    return {"service": "hallo-wrapper", "version": "0.1.0", "status": st,
            "ready": st == "ready",
            "details": {"runtime": rt, "assets": a}, "time": time.time()}


class HalloRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    image_path: str = Field(..., max_length=2000)
    audio_path: str = Field(..., max_length=2000)
    output_path: str = Field(..., max_length=2000)
    width: int = Field(default=512, ge=256, le=1024)
    height: int = Field(default=512, ge=256, le=1024)
    seed: int | None = None


class HalloError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error_code: Literal["runtime_missing", "assets_missing", "gpu_unavailable",
                        "generation_failed", "storage_failed"]
    detail: str


def _err(c, ec, d):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=c,
                        content=HalloError(error_code=ec, detail=d).model_dump())  # type: ignore[arg-type]


@app.post("/hallo/generate")
async def generate(body: HalloRequest):
    rt = _check_runtime(); a = _check_assets()
    st = _overall_status(rt, a)
    if st == "runtime_missing":
        return _err(503, "runtime_missing", "torch/diffusers/source missing")
    if st == "gpu_unavailable":
        return _err(503, "gpu_unavailable", "CUDA not visible")
    if st == "assets_missing":
        return _err(503, "assets_missing", f"weights missing under {_models_root()}")

    import glob
    import shutil

    out = Path(body.output_path)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _err(500, "storage_failed", str(exc))

    # hallo2's inference_long.py has NO --save_path; it reads everything from a
    # YAML config (model paths relative to ./pretrained_models, plus save_path)
    # and --source_image/--driving_audio override the inputs. So we: (1) point
    # ./pretrained_models at our weights, (2) write a temp config whose
    # save_path is a writable work dir, (3) run, (4) move the produced mp4 to out.
    src = _source_dir()
    pm = src / "pretrained_models"
    if not pm.exists():
        try:
            pm.symlink_to(_models_root())
        except OSError:
            pass
    work = out.parent / "hallo_work"
    cfg_path = out.parent / "hallo_config.yaml"
    try:
        from omegaconf import OmegaConf
        cfg = OmegaConf.load(str(src / "configs" / "inference" / "long.yaml"))
        cfg.save_path = str(work)
        cfg.cache_path = str(out.parent / ".hallo_cache")
        # Fewer diffusion steps so it's feasible on a 24GB GPU (40 is far too
        # slow there). Tunable via HALLO_INFER_STEPS; the 128GB box can raise it.
        cfg.inference_steps = int(os.environ.get("HALLO_INFER_STEPS", "12"))
        OmegaConf.save(cfg, str(cfg_path))
    except Exception as exc:  # noqa: BLE001
        return _err(500, "generation_failed", f"config build failed: {exc}")

    cmd = [
        sys.executable, str(src / "scripts" / "inference_long.py"),
        "-c", str(cfg_path),
        "--source_image", body.image_path,
        "--driving_audio", body.audio_path,
    ]
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(cmd, cwd=str(src),
                              capture_output=True, text=True,
                              timeout=int(os.environ.get("HALLO_INFER_TIMEOUT", "1800")))
        elapsed = time.perf_counter() - t0
        if proc.returncode != 0:
            return _err(500, "generation_failed",
                        f"inference exit={proc.returncode}: {proc.stderr[-300:]}")
        # Find the produced mp4 under the work dir and move it to ``out``.
        produced = sorted(glob.glob(str(work / "**" / "*.mp4"), recursive=True),
                          key=lambda p: Path(p).stat().st_size if Path(p).is_file() else 0)
        if not produced:
            return _err(500, "generation_failed",
                        f"inference finished but no mp4 under {work}. tail: {proc.stdout[-200:]}")
        shutil.move(produced[-1], str(out))
        return {"status": "completed", "output_path": str(out),
                "size_bytes": out.stat().st_size if out.is_file() else 0,
                "duration_seconds": elapsed}
    except subprocess.TimeoutExpired:
        return _err(500, "generation_failed", "inference timeout")
    except Exception as exc:
        tb = traceback.format_exception_only(type(exc), exc)[-1].strip()
        return _err(500, "generation_failed", tb)
