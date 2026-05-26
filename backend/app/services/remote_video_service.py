"""Remote video generation — drive an external engine over the LAN
(e.g. GB10 / ThinkStation running Wan2.2) and register the resulting MP4 as a
local video artifact.

Differs from image generation in two ways:
  1. Auth header is ``X-API-Key`` (not ``Authorization: Bearer``).
  2. Video is too large for inline base64 → the engine returns an *output path*
     on its own filesystem; we download the bytes via ``GET /file?path=..&key=..``
     and save them into the local ``/storage/artifacts`` volume.

The engine call is **synchronous and slow** (~10–16 min/clip): the POST blocks
until the task finishes and returns the terminal task object. We use a long,
configurable timeout (``REMOTE_VIDEO_TIMEOUT_SECONDS``) and, as a safety net,
poll ``GET /tasks/{id}`` if the POST ever returns a non-terminal status.

Scope: text→video (t2v) only for now. image→video (i2v) and speech→video (s2v)
need the input media uploaded to the engine first — a separate follow-up.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import uuid
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import artifact_service

logger = logging.getLogger(__name__)

BASE_URL_ENV = "REMOTE_IMAGE_BASE_URL"   # same engine box as image gen
API_KEY_ENV = "REMOTE_ENGINE_API_KEY"
_TERMINAL = {"completed", "error", "failed", "cancelled"}


class RemoteVideoError(Exception):
    """Categorised remote-video failure. ``error_code`` mirrors the video API."""

    def __init__(self, error_code: str, detail: str) -> None:
        super().__init__(detail)
        self.error_code = error_code
        self.detail = detail


def _base_url() -> str:
    v = os.environ.get(BASE_URL_ENV, "").strip().rstrip("/")
    if not v:
        raise RemoteVideoError(
            "video_provider_not_configured",
            f"Remote engine not configured. Set {BASE_URL_ENV} and {API_KEY_ENV}.",
        )
    return v


def _headers() -> dict[str, str]:
    key = os.environ.get(API_KEY_ENV, "").strip()
    if not key:
        raise RemoteVideoError(
            "video_provider_not_configured",
            f"{API_KEY_ENV} is empty — the remote engine requires an API key.",
        )
    return {"X-API-Key": key, "Content-Type": "application/json", "Accept": "application/json"}


def _storage_root() -> Path:
    return Path(os.environ.get("ARTIFACTS_LOCAL_ROOT", "/storage/artifacts"))


async def _poll_until_done(client: httpx.AsyncClient, base: str, task_id: str) -> dict:
    """Poll ``/tasks/{id}`` until the task reaches a terminal status."""
    deadline = asyncio.get_event_loop().time() + float(
        os.environ.get("REMOTE_VIDEO_TIMEOUT_SECONDS", "1800")
    )
    while asyncio.get_event_loop().time() < deadline:
        r = await client.get(f"{base}/tasks/{task_id}", headers=_headers())
        if r.status_code // 100 == 2:
            task = (r.json() or {}).get("task") or r.json()
            if str(task.get("status")) in _TERMINAL:
                return task
        await asyncio.sleep(5)
    raise RemoteVideoError("generation_failed", f"remote task {task_id} timed out")


async def generate_video_remote(
    session: AsyncSession,
    *,
    prompt: str,
    backend: str = "main",
    task: str = "t2v-A14B",
    size: str = "832*480",
    steps: int = 20,
    job_id: uuid.UUID | None = None,
) -> dict:
    """Submit a text→video job to the remote engine, download the MP4, and
    register it as a local ``video`` artifact. Returns a small result dict.

    Raises :class:`RemoteVideoError` (categorised) on any failure.
    """
    base = _base_url()
    body = {"backend": backend, "task": task, "prompt": prompt, "size": size, "steps": steps}
    timeout_s = float(os.environ.get("REMOTE_VIDEO_TIMEOUT_SECONDS", "1800"))
    logger.info(
        "remote_video.submit backend=%s task=%s size=%s steps=%s job_id=%s",
        backend, task, size, steps, job_id,
    )
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        try:
            resp = await client.post(f"{base}/generate/video", json=body, headers=_headers())
        except Exception as exc:
            raise RemoteVideoError(
                "generation_failed", f"HTTP call to remote engine failed: {type(exc).__name__}: {exc}"
            ) from exc
        if resp.status_code == 401:
            raise RemoteVideoError("video_provider_not_configured", "Remote engine rejected the API key (401).")
        if resp.status_code // 100 != 2:
            raise RemoteVideoError("generation_failed", f"remote engine HTTP {resp.status_code}: {resp.text[:300]}")

        task_obj = (resp.json() or {}).get("task") or {}
        status = str(task_obj.get("status", "")).lower()
        if status and status not in _TERMINAL:
            # Non-terminal → poll (defensive; the engine usually blocks to completion).
            task_obj = await _poll_until_done(client, base, task_obj.get("task_id", ""))
            status = str(task_obj.get("status", "")).lower()

        if status != "completed":
            tail = (task_obj.get("log") or task_obj.get("error") or "")
            raise RemoteVideoError(
                "generation_failed",
                f"remote video task ended status={status!r}. Engine detail: {str(tail)[:400]}",
            )

        outputs = task_obj.get("outputs") or []
        if not outputs:
            raise RemoteVideoError("generation_failed", "remote task completed but returned no outputs")
        remote_path = outputs[0]

        # Download the produced file from the engine's filesystem.
        try:
            dl = await client.get(
                f"{base}/file", params={"path": remote_path, "key": os.environ.get(API_KEY_ENV, "")}
            )
        except Exception as exc:
            raise RemoteVideoError("storage_failed", f"download of {remote_path} failed: {exc}") from exc
        if dl.status_code // 100 != 2:
            raise RemoteVideoError("storage_failed", f"download HTTP {dl.status_code} for {remote_path}")
        video_bytes = dl.content

    # Persist locally + register the artifact.
    out_dir = _storage_root() / "remote_video"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{uuid.uuid4()}.mp4"
    out_path.write_bytes(video_bytes)
    checksum = hashlib.sha256(video_bytes).hexdigest()
    artifact = await artifact_service.register_artifact(
        session,
        job_id=job_id,
        artifact_type="video",
        uri=str(out_path),
        local_path=str(out_path),
        mime_type="video/mp4",
        checksum_sha256=checksum,
        size_bytes=len(video_bytes),
        metadata_json={
            "remote": True,
            "engine_backend": backend,
            "engine_task": task,
            "remote_output_path": remote_path,
            "task_id": task_obj.get("task_id"),
        },
    )
    logger.info(
        "remote_video.done artifact_id=%s bytes=%s task_id=%s",
        artifact.id, len(video_bytes), task_obj.get("task_id"),
    )
    return {
        "status": "completed",
        "artifact_id": str(artifact.id),
        "size_bytes": len(video_bytes),
        "task_id": task_obj.get("task_id"),
        "remote_output_path": remote_path,
    }
