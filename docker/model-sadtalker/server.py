"""SadTalker GPU HTTP wrapper — Phase 10B.

Mirrors the F5TTS-Ro wrapper pattern (docker/model-tts-ro/server.py).
The light backend posts to ``/sadtalker/generate`` over HTTP; this
service does the heavy CUDA work and writes an MP4 on the shared
``/storage/artifacts`` volume. The backend then registers the artifact.

Endpoints:
- ``GET /health`` — always 200, payload describes runtime + weight state.
- ``POST /sadtalker/generate`` — runs SadTalker against image + audio.

Safety contract:
- No fake MP4. If torch / SadTalker / weights are missing, the endpoint
  returns a categorised error and writes nothing.
- No auto-download of model weights.
- Cleans partial files on failure.
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field


app = FastAPI(title="SadTalker GPU wrapper", version="0.1.0")


# ---------------------------------------------------------------------------
# Readiness probes — stdlib only at module load. Torch import is lazy.
# ---------------------------------------------------------------------------


def _models_root() -> Path:
    return Path(os.environ.get("SADTALKER_MODELS_ROOT", "/models/lipsync/sadtalker"))


def _source_dir() -> Path:
    return Path(os.environ.get("SADTALKER_SOURCE_DIR", "/opt/sadtalker"))


def _result_dir() -> Path:
    return Path(os.environ.get("SADTALKER_RESULT_DIR", "/storage/artifacts/sadtalker"))


_REQUIRED_WEIGHTS = (
    "checkpoints/mapping_00109-model.pth.tar",
    "checkpoints/mapping_00229-model.pth.tar",
    "checkpoints/SadTalker_V0.0.2_256.safetensors",
    "checkpoints/SadTalker_V0.0.2_512.safetensors",
    "gfpgan/GFPGANv1.4.pth",
)


def _check_runtime() -> dict[str, Any]:
    import importlib.util

    torch_spec = importlib.util.find_spec("torch")
    cv2_spec = importlib.util.find_spec("cv2")
    info: dict[str, Any] = {
        "python": sys.version.split()[0],
        "torch_available": torch_spec is not None,
        "cv2_available": cv2_spec is not None,
        "source_dir": str(_source_dir()),
        "source_dir_exists": _source_dir().is_dir(),
        "inference_script_exists": (_source_dir() / "inference.py").is_file(),
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
    return info


def _check_assets() -> dict[str, Any]:
    root = _models_root()
    missing: list[str] = []
    sizes: dict[str, int] = {}
    for rel in _REQUIRED_WEIGHTS:
        p = root / rel
        if p.is_file():
            sizes[rel] = p.stat().st_size
        else:
            missing.append(rel)
    return {
        "models_root": str(root),
        "models_root_exists": root.is_dir(),
        "required": list(_REQUIRED_WEIGHTS),
        "present_sizes": sizes,
        "missing": missing,
    }


def _readiness() -> tuple[str, dict[str, Any]]:
    rt = _check_runtime()
    assets = _check_assets()
    if not rt["torch_available"] or not rt["cv2_available"]:
        return "runtime_missing", {"runtime": rt, "assets": assets}
    if not rt["source_dir_exists"] or not rt["inference_script_exists"]:
        return "runtime_missing", {"runtime": rt, "assets": assets}
    if not rt.get("torch_cuda_available"):
        return "gpu_unavailable", {"runtime": rt, "assets": assets}
    if not assets["models_root_exists"] or assets["missing"]:
        return "assets_missing", {"runtime": rt, "assets": assets}
    return "ready", {"runtime": rt, "assets": assets}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SadTalkerGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_path: str = Field(..., description="Absolute path to the source image.")
    audio_path: str = Field(..., description="Absolute path to the driver audio (WAV).")
    output_path: str = Field(..., description="Absolute path where the MP4 should be written.")
    target_duration_seconds: int | None = Field(default=None, ge=1, le=600)
    model_id: str | None = Field(default=None, max_length=160)
    size: Literal[256, 512] = 256
    enhancer: Literal["", "gfpgan", "RestoreFormer"] = "gfpgan"
    preprocess: Literal["crop", "full", "resize", "extcrop", "extfull"] = "crop"
    still: bool = True


class SadTalkerGenerateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "completed",
        "runtime_missing",
        "assets_missing",
        "gpu_unavailable",
        "generation_failed",
    ]
    error_code: str | None = None
    message: str | None = None
    output_path: str | None = None
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    size_bytes: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# /health — always 200
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, Any]:
    status, details = _readiness()
    return {
        "service": "sadtalker-wrapper",
        "version": app.version,
        "status": status,
        "ready": status == "ready",
        "details": details,
        "env": {
            "SADTALKER_MODELS_ROOT": os.environ.get("SADTALKER_MODELS_ROOT", "<unset>"),
            "SADTALKER_SOURCE_DIR": os.environ.get("SADTALKER_SOURCE_DIR", "<unset>"),
            "SADTALKER_RESULT_DIR": os.environ.get("SADTALKER_RESULT_DIR", "<unset>"),
        },
        "time": time.time(),
    }


# ---------------------------------------------------------------------------
# /sadtalker/generate — heavy path
# ---------------------------------------------------------------------------


def _fail(
    status: str,
    *,
    error_code: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> SadTalkerGenerateResponse:
    return SadTalkerGenerateResponse(
        status=status,  # type: ignore[arg-type]
        error_code=error_code,
        message=message,
        metadata=metadata or {},
    )


def _ffprobe_meta(mp4: Path) -> dict[str, Any]:
    """Best-effort ffprobe → (width, height, duration). Returns an empty
    dict on failure; the backend will still register the artifact with
    whatever dimensions it can derive on its own.
    """
    try:
        out = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_streams",
                "-show_format",
                str(mp4),
            ],
            stderr=subprocess.STDOUT,
            timeout=30,
        ).decode("utf-8", errors="replace")
        import json

        data = json.loads(out)
    except Exception as exc:  # pragma: no cover
        return {"ffprobe_error": f"{type(exc).__name__}: {exc}"}

    width = height = None
    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
            width = int(s.get("width") or 0) or None
            height = int(s.get("height") or 0) or None
            break
    duration = None
    fmt = data.get("format") or {}
    if fmt.get("duration"):
        try:
            duration = float(fmt["duration"])
        except (TypeError, ValueError):
            duration = None
    return {
        "width": width,
        "height": height,
        "duration_seconds": duration,
        "format_name": fmt.get("format_name"),
    }


@app.post("/sadtalker/generate", response_model=SadTalkerGenerateResponse)
def sadtalker_generate(payload: SadTalkerGenerateRequest) -> SadTalkerGenerateResponse:
    ready, details = _readiness()
    if ready != "ready":
        code_map = {
            "runtime_missing": "video_runtime_missing",
            "gpu_unavailable": "video_gpu_missing",
            "assets_missing": "video_assets_missing",
        }
        return _fail(
            ready,
            error_code=code_map.get(ready, "video_runtime_missing"),
            message=f"SadTalker wrapper not ready: {ready}",
            metadata=details,
        )

    image_path = Path(payload.image_path)
    audio_path = Path(payload.audio_path)
    out_path = Path(payload.output_path)

    if not image_path.is_file():
        return _fail(
            "generation_failed",
            error_code="video_generation_failed",
            message=f"image not readable at {image_path}",
            metadata=details,
        )
    if not audio_path.is_file():
        return _fail(
            "generation_failed",
            error_code="video_generation_failed",
            message=f"audio not readable at {audio_path}",
            metadata=details,
        )

    # SadTalker writes into a result_dir then names the output after the
    # input image. We use a per-call subdir so concurrent calls don't
    # collide, then move the produced MP4 to the requested output_path.
    job_tag = uuid.uuid4().hex[:12]
    work_dir = _result_dir() / job_tag
    work_dir.mkdir(parents=True, exist_ok=True)

    # Build the SadTalker CLI invocation. The upstream script lives at
    # /opt/sadtalker/inference.py and uses the local ./checkpoints +
    # ./gfpgan/weights symlinks (created at image build time).
    src_dir = _source_dir()
    cmd = [
        "python",
        "inference.py",
        "--driven_audio",
        str(audio_path),
        "--source_image",
        str(image_path),
        "--result_dir",
        str(work_dir),
        "--size",
        str(payload.size),
        "--preprocess",
        payload.preprocess,
    ]
    if payload.still:
        cmd.append("--still")
    if payload.enhancer:
        cmd.extend(["--enhancer", payload.enhancer])

    started = time.time()
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(src_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=int(os.environ.get("SADTALKER_INFER_TIMEOUT", "900")),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        return _fail(
            "generation_failed",
            error_code="video_generation_failed",
            message=f"SadTalker timed out after {exc.timeout}s",
            metadata=details,
        )
    except Exception as exc:  # pragma: no cover — defensive
        shutil.rmtree(work_dir, ignore_errors=True)
        return _fail(
            "generation_failed",
            error_code="video_generation_failed",
            message=f"subprocess error: {type(exc).__name__}: {exc}",
            metadata={**details, "traceback": traceback.format_exc()[-1200:]},
        )
    elapsed = time.time() - started
    stdout_tail = (completed.stdout or b"").decode("utf-8", errors="replace")[-2000:]

    if completed.returncode != 0:
        shutil.rmtree(work_dir, ignore_errors=True)
        return _fail(
            "generation_failed",
            error_code="video_generation_failed",
            message=(
                f"SadTalker exited with code {completed.returncode}. "
                f"Tail: {stdout_tail[-800:]}"
            ),
            metadata={
                **details,
                "elapsed_seconds": elapsed,
                "cmd": " ".join(shlex.quote(p) for p in cmd),
                "stdout_tail": stdout_tail,
            },
        )

    # SadTalker writes a timestamped subdirectory under work_dir
    # containing the final MP4. Find the largest .mp4 the run produced.
    mp4s = sorted(
        (p for p in work_dir.rglob("*.mp4") if p.stat().st_size > 0),
        key=lambda p: p.stat().st_size,
        reverse=True,
    )
    if not mp4s:
        return _fail(
            "generation_failed",
            error_code="video_generation_failed",
            message="SadTalker returned 0 but no MP4 landed under result_dir",
            metadata={
                **details,
                "elapsed_seconds": elapsed,
                "work_dir": str(work_dir),
                "stdout_tail": stdout_tail,
            },
        )
    chosen = mp4s[0]

    # Move the MP4 into the caller's requested output_path (on the shared
    # /storage/artifacts volume). Then drop the work_dir.
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(chosen), str(out_path))
    except OSError as exc:
        return _fail(
            "generation_failed",
            error_code="video_generation_failed",
            message=f"could not move MP4 to {out_path}: {exc}",
            metadata={**details, "work_dir": str(work_dir)},
        )
    shutil.rmtree(work_dir, ignore_errors=True)

    size_bytes = out_path.stat().st_size
    probe = _ffprobe_meta(out_path)
    return SadTalkerGenerateResponse(
        status="completed",
        output_path=str(out_path),
        size_bytes=size_bytes,
        width=probe.get("width"),
        height=probe.get("height"),
        duration_seconds=probe.get("duration_seconds"),
        metadata={
            "elapsed_seconds": elapsed,
            "size_setting": payload.size,
            "enhancer": payload.enhancer,
            "preprocess": payload.preprocess,
            "still": payload.still,
            "format_name": probe.get("format_name"),
            "runtime": details.get("runtime", {}),
            "model_id": payload.model_id,
            "target_duration_seconds": payload.target_duration_seconds,
        },
    )
