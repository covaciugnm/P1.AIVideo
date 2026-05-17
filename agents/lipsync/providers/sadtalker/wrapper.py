"""Phase 11C — HTTP client for the ``model-sadtalker`` GPU wrapper.

This module is the orchestrator-side counterpart of
``backend/app/api/video.py::_run_sadtalker_via_wrapper``. It lives in
its own file so the strict Phase 7B test that bans ``urllib.request``
from ``provider.py`` (anti-auto-download policy) stays intact — this
file does open a URL, but only against the operator-controlled
``SADTALKER_BASE_URL`` (the local GPU service), never the public
internet. The wrapper itself enforces ``F5TTS_RO_ALLOW_AUTO_DOWNLOAD``
/ SadTalker's "no auto-download" rule on its side.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path


def wrapper_status(base_url: str) -> dict | None:
    """Probe the wrapper's ``/health`` endpoint and translate the
    response into our SadTalker status vocabulary.

    Returns ``None`` on transport failure so the caller can fall back
    to the in-process readiness check.
    """
    url = base_url.rstrip("/") + "/health"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(
            req,
            timeout=int(os.environ.get("SADTALKER_HTTP_TIMEOUT", "5")),
        ) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None

    details = body.get("details", {})
    runtime = details.get("runtime", {})
    assets = details.get("assets", {})
    wrapper_state = body.get("status", "unknown")

    if wrapper_state == "ready":
        return {"status": "ready", "details": details, "wrapper_url": base_url}
    if wrapper_state == "runtime_missing":
        return {
            "status": "runtime_missing",
            "details": details,
            "wrapper_url": base_url,
        }
    if wrapper_state == "assets_missing":
        return {
            "status": "assets_missing",
            "details": details,
            "wrapper_url": base_url,
        }
    if wrapper_state == "gpu_unavailable" or not runtime.get(
        "torch_cuda_available", True
    ):
        return {
            "status": "gpu_unavailable",
            "details": details,
            "wrapper_url": base_url,
        }
    if assets.get("missing"):
        return {
            "status": "assets_missing",
            "details": details,
            "wrapper_url": base_url,
        }
    return {
        "status": "not_implemented",
        "details": details,
        "wrapper_url": base_url,
    }


def generate_via_wrapper(
    *,
    base_url: str,
    image_path: Path,
    audio_path: Path,
    output_dir: Path,
    target_duration_seconds: int | None,
    model_id: str | None,
    details: dict,
) -> dict:
    """Send the lipsync request to the model-sadtalker wrapper over
    HTTP and return the same shape ``_attempt_real_inference`` would.

    The wrapper writes the MP4 onto the shared artifacts volume, so the
    orchestrator can checksum + register it identically to the
    in-process path. On any wrapper failure we return a categorised
    dict; the caller translates that into ``StageRejection``.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        output_dir.chmod(0o777)
    except OSError:
        pass
    out_name = f"sadtalker_{uuid.uuid4().hex}.mp4"
    output_path = output_dir / out_name

    body = {
        "image_path": str(image_path),
        "audio_path": str(audio_path),
        "output_path": str(output_path),
        "target_duration_seconds": target_duration_seconds,
        "model_id": model_id,
        "size": 256,
        "enhancer": "gfpgan",
        "preprocess": "crop",
        "still": True,
    }
    url = base_url.rstrip("/") + "/sadtalker/generate"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    timeout = int(os.environ.get("SADTALKER_HTTP_TIMEOUT", "1200"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload_bytes = resp.read()
            wrapper_payload = json.loads(payload_bytes.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_text = exc.read().decode("utf-8", errors="replace")[:500]
        return {
            "status": "failed",
            "error_code": "video_generation_failed",
            "message": (
                f"model-sadtalker wrapper returned HTTP {exc.code}: {err_text}"
            ),
            "details": details,
        }
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {
            "status": "failed",
            "error_code": "video_generation_failed",
            "message": (
                f"model-sadtalker wrapper unreachable at {url}: "
                f"{type(exc).__name__}: {exc}"
            ),
            "details": details,
        }

    wrapper_state = wrapper_payload.get("status", "unknown")
    if wrapper_state != "completed":
        return {
            "status": wrapper_state,
            "error_code": wrapper_payload.get("error_code")
            or "video_generation_failed",
            "message": wrapper_payload.get(
                "message", "wrapper returned non-completed status"
            ),
            "details": {**details, "wrapper_payload": wrapper_payload},
        }

    if not output_path.is_file():
        return {
            "status": "failed",
            "error_code": "video_generation_failed",
            "message": (
                f"wrapper reported completion but no MP4 found at {output_path}"
            ),
            "details": {**details, "wrapper_payload": wrapper_payload},
        }

    return {
        "status": "completed",
        "output_path": str(output_path),
        "model_id": model_id,
        "target_duration_seconds": target_duration_seconds,
        "details": {**details, "wrapper_payload": wrapper_payload},
    }
