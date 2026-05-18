"""Video generator API — Phase 6A contract + Phase 7B categorised errors
+ Phase 7D real-inference artifact registration.

POST /api/v1/video/generate

- Phase 6A: validates inputs, returns metadata-only ``not_implemented``.
- Phase 7B: for ``sadtalker``, surfaces categorised readiness codes
  (``video_runtime_missing`` / ``video_assets_missing`` /
  ``video_gpu_missing`` / ``video_provider_not_configured`` /
  ``video_provider_not_implemented``).
- Phase 7D: when all seven SadTalker gates are satisfied and the
  provider returns ``completed``, registers an ``ArtifactType.video``
  row and returns ``status="completed"`` with ``output_video_artifact_id``.

Real inference is gated behind ``SADTALKER_ENABLE_REAL_INFERENCE=true``
+ ``RUN_REAL_SADTALKER=1`` AND host-level torch + CUDA + weights. The
default light backend will never reach the real path.
"""
from __future__ import annotations

import hashlib
import logging
import os
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

logger = logging.getLogger(__name__)
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.enums import ArtifactType

from app.core.config import settings
from app.core.deps import get_db_session
from app.models.artifact import Artifact
from app.models.job import Job
from app.services import artifact_service

router = APIRouter(prefix="/api/v1/video", tags=["video"])


_KNOWN_VIDEO_PROVIDERS = {"sadtalker", "musetalk", "wav2lip"}


VideoStatus = Literal[
    "accepted",
    "not_configured",
    "missing_inputs",
    "failed",
    "completed",
    "not_implemented",
]


# Phase 7B categorised error codes for the sadtalker provider. The
# default state (real-inference gate off) keeps ``provider_not_implemented``
# for Phase 6A backwards compatibility. The new ``video_*`` codes only
# surface when the operator has explicitly opted in to real inference
# (RUN_REAL_SADTALKER=1 + SADTALKER_ENABLE_REAL_INFERENCE=true) but is
# missing weights / torch / CUDA. See docs/runbooks/sadtalker-runtime.md.
_VIDEO_ERROR_CODES = (
    "video_runtime_missing",
    "video_assets_missing",
    "video_gpu_missing",
    "video_provider_not_configured",
    "video_provider_not_implemented",
    "video_generation_failed",
    # Phase 6A pre-Phase-7B codes — preserved for the catalog default.
    "provider_not_implemented",
    "unknown_provider",
)


def _precheck_face_image(
    img: Artifact, payload: "VideoGenerationRequest"
) -> "VideoGenerationResult | None":
    """Phase 11E — refuse images SadTalker has zero chance of using
    (too small for the face cropper / no local file). Called only when
    the operator picked SadTalker as the video provider so the prior
    error-code path (``video_provider_not_configured`` etc.) keeps its
    priority on misconfigured providers.

    Returns a ``VideoGenerationResult`` describing the failure when the
    image is unsuitable, or ``None`` when the image passes the
    precheck and we should proceed to invoke the provider.
    """
    if img.width is None or img.height is None or img.width < 256 or img.height < 256:
        return VideoGenerationResult(
            status="missing_inputs",
            provider_id=payload.provider_id,
            model_id=payload.model_id,
            job_id=payload.job_id,
            error_code="video_face_image_too_small",
            message=(
                f"image is {img.width}x{img.height}; SadTalker requires "
                "at least 256x256 with a visible front-facing portrait. "
                "Upload a larger, clearer face image."
            ),
        )
    if img.local_path is None or not Path(img.local_path).is_file():
        return VideoGenerationResult(
            status="missing_inputs",
            provider_id=payload.provider_id,
            model_id=payload.model_id,
            job_id=payload.job_id,
            error_code="image_artifact_missing_file",
            message=(
                f"image artifact {payload.image_artifact_id} has no readable "
                "local_path — the file must live on the shared artifacts "
                "volume."
            ),
        )
    return None


def _sadtalker_result_from_status(
    status: str,
    details: dict,
    *,
    provider_id: str,
    model_id: str | None,
    job_id,
    image_artifact_id,
    audio_artifact_id,
    edit_plan_artifact_id,
    target_duration_seconds: int,
    img_dims: tuple[int | None, int | None],
    audio_duration_seconds: float | None,
) -> "VideoGenerationResult":
    """Translate a SadTalker ``inspect_status()`` result into the
    metadata-only ``VideoGenerationResult`` shape Phase 6A pinned.

    Phase 7B never returns ``completed`` here — even ``ready`` collapses
    back to ``not_implemented`` because the real path lands in Phase 7D.
    """
    base_metadata = {
        "image_artifact_id": str(image_artifact_id),
        "audio_artifact_id": str(audio_artifact_id),
        "edit_plan_artifact_id": (
            str(edit_plan_artifact_id) if edit_plan_artifact_id is not None else None
        ),
        "target_duration_seconds": target_duration_seconds,
        "image_dims": [img_dims[0], img_dims[1]] if img_dims[0] else None,
        "audio_duration_seconds": audio_duration_seconds,
        "sadtalker": {
            "inspect_status": status,
            "real_inference_enabled": status not in {"not_implemented"},
            "details": details,
        },
    }

    if status == "not_implemented":
        return VideoGenerationResult(
            status="not_implemented",
            provider_id=provider_id,
            model_id=model_id,
            job_id=job_id,
            error_code="provider_not_implemented",
            message=(
                f"video provider {provider_id!r} is a Phase 3A stub; "
                "real inference + GPU integration land in a later phase. "
                "Inputs validated; no MP4 produced."
            ),
            metadata=base_metadata,
        )
    if status == "not_configured":
        return VideoGenerationResult(
            status="not_configured",
            provider_id=provider_id,
            model_id=model_id,
            job_id=job_id,
            error_code="video_provider_not_configured",
            message=(
                "SadTalker is not configured: SADTALKER_MODELS_ROOT is unset. "
                "Set it in .env (see docs/runbooks/sadtalker-runtime.md)."
            ),
            metadata=base_metadata,
        )
    if status == "assets_missing":
        missing = details.get("assets", {}).get("missing", [])
        return VideoGenerationResult(
            status="not_configured",
            provider_id=provider_id,
            model_id=model_id,
            job_id=job_id,
            error_code="video_assets_missing",
            message=(
                "SadTalker weights are not on disk. Missing: "
                f"{', '.join(missing) if missing else '(none reported)'}. "
                "Place the files manually under SADTALKER_MODELS_ROOT "
                "(see docs/runbooks/sadtalker-runtime.md). No auto-download."
            ),
            metadata=base_metadata,
        )
    if status == "runtime_missing":
        return VideoGenerationResult(
            status="not_configured",
            provider_id=provider_id,
            model_id=model_id,
            job_id=job_id,
            error_code="video_runtime_missing",
            message=(
                "SadTalker runtime is unavailable: torch is not importable in "
                "this backend image. The default light backend is intentionally "
                "torch-free; SadTalker runs from the GPU image (Dockerfile.cuda)."
            ),
            metadata=base_metadata,
        )
    if status == "gpu_unavailable":
        return VideoGenerationResult(
            status="not_configured",
            provider_id=provider_id,
            model_id=model_id,
            job_id=job_id,
            error_code="video_gpu_missing",
            message=(
                "SadTalker runtime is present but no CUDA device is visible. "
                "Check the NVIDIA driver + NVIDIA Container Toolkit (see "
                "docs/runbooks/gpu-runtime.md)."
            ),
            metadata=base_metadata,
        )
    # status == "ready": Phase 7B never runs real inference.
    return VideoGenerationResult(
        status="not_implemented",
        provider_id=provider_id,
        model_id=model_id,
        job_id=job_id,
        error_code="provider_not_implemented",
        message=(
            "SadTalker is ready (weights + torch + GPU all present + flags on) "
            "but Phase 7B intentionally never invokes the real path. Phase 7D "
            "ships the actual torch.cuda call."
        ),
        metadata=base_metadata,
    )


class VideoGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: uuid.UUID
    image_artifact_id: uuid.UUID
    audio_artifact_id: uuid.UUID
    provider_id: str = Field(default="sadtalker", max_length=80)
    model_id: str | None = Field(default=None, max_length=160)
    target_duration_seconds: int = Field(..., ge=1, le=600)
    edit_plan_artifact_id: uuid.UUID | None = None
    metadata: dict = Field(default_factory=dict)


class VideoGenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: VideoStatus
    provider_id: str
    model_id: str | None = None
    job_id: uuid.UUID
    output_video_artifact_id: uuid.UUID | None = None
    error_code: str | None = None
    message: str = ""
    metadata: dict = Field(default_factory=dict)


@router.post(
    "/generate",
    response_model=VideoGenerationResult,
)
async def video_generate(
    payload: VideoGenerationRequest,
    session: AsyncSession = Depends(get_db_session),
) -> VideoGenerationResult:
    logger.info(
        "video.generate.start job_id=%s provider=%s model=%s image_artifact=%s audio_artifact=%s target_dur=%s",
        payload.job_id, payload.provider_id, payload.model_id,
        payload.image_artifact_id, payload.audio_artifact_id, payload.target_duration_seconds,
    )
    # 1. Job exists.
    job_row = await session.execute(select(Job).where(Job.id == payload.job_id))
    if job_row.scalar_one_or_none() is None:
        logger.warning("video.generate.not_found job_id=%s", payload.job_id)
        raise HTTPException(status_code=404, detail="job not found")

    # 2. Image artifact exists + correct type.
    img_row = await session.execute(
        select(Artifact).where(Artifact.id == payload.image_artifact_id)
    )
    img = img_row.scalar_one_or_none()
    if img is None:
        return VideoGenerationResult(
            status="missing_inputs",
            provider_id=payload.provider_id,
            model_id=payload.model_id,
            job_id=payload.job_id,
            error_code="image_artifact_not_found",
            message=f"image artifact {payload.image_artifact_id} not found",
        )
    if img.artifact_type != "image":
        return VideoGenerationResult(
            status="missing_inputs",
            provider_id=payload.provider_id,
            model_id=payload.model_id,
            job_id=payload.job_id,
            error_code="wrong_image_artifact_type",
            message=f"artifact {payload.image_artifact_id} is type {img.artifact_type!r}, expected 'image'",
        )

    # 3. Audio artifact exists + correct type.
    aud_row = await session.execute(
        select(Artifact).where(Artifact.id == payload.audio_artifact_id)
    )
    aud = aud_row.scalar_one_or_none()
    if aud is None:
        return VideoGenerationResult(
            status="missing_inputs",
            provider_id=payload.provider_id,
            model_id=payload.model_id,
            job_id=payload.job_id,
            error_code="audio_artifact_not_found",
            message=f"audio artifact {payload.audio_artifact_id} not found",
        )
    if aud.artifact_type != "audio":
        return VideoGenerationResult(
            status="missing_inputs",
            provider_id=payload.provider_id,
            model_id=payload.model_id,
            job_id=payload.job_id,
            error_code="wrong_audio_artifact_type",
            message=f"artifact {payload.audio_artifact_id} is type {aud.artifact_type!r}, expected 'audio'",
        )

    # 4. Optional edit_plan artifact validation.
    if payload.edit_plan_artifact_id is not None:
        ep_row = await session.execute(
            select(Artifact).where(Artifact.id == payload.edit_plan_artifact_id)
        )
        ep = ep_row.scalar_one_or_none()
        if ep is None:
            return VideoGenerationResult(
                status="missing_inputs",
                provider_id=payload.provider_id,
                model_id=payload.model_id,
                job_id=payload.job_id,
                error_code="edit_plan_artifact_not_found",
                message=f"edit_plan artifact {payload.edit_plan_artifact_id} not found",
            )
        if ep.artifact_type != "edit_plan":
            return VideoGenerationResult(
                status="missing_inputs",
                provider_id=payload.provider_id,
                model_id=payload.model_id,
                job_id=payload.job_id,
                error_code="wrong_edit_plan_artifact_type",
                message=f"artifact {payload.edit_plan_artifact_id} is type {ep.artifact_type!r}, expected 'edit_plan'",
            )

    # 5. Provider exists in the catalog.
    if payload.provider_id not in _KNOWN_VIDEO_PROVIDERS:
        return VideoGenerationResult(
            status="not_configured",
            provider_id=payload.provider_id,
            model_id=payload.model_id,
            job_id=payload.job_id,
            error_code="unknown_provider",
            message=(
                f"video provider {payload.provider_id!r} is not in the known "
                f"catalog ({sorted(_KNOWN_VIDEO_PROVIDERS)})."
            ),
        )

    # 6. Provider-specific dispatch.
    #
    # ``sadtalker`` is the first provider hardened end-to-end:
    #   Phase 7B → categorised readiness errors, never real inference.
    #   Phase 7D → if all seven gates align, actually generate the MP4
    #             and register an ``ArtifactType.video`` row.
    #
    # Phase 6A's invariant — default-state sadtalker returns
    # ``not_implemented`` / ``provider_not_implemented`` — is preserved
    # because real-inference flags default to off; the provider's
    # ``inspect_status()`` short-circuits to ``not_implemented``.
    if payload.provider_id == "sadtalker":
        from agents.lipsync.providers.sadtalker.provider import SadTalkerProvider

        provider = SadTalkerProvider()

        # Phase 11E — image suitability precheck. Once we KNOW
        # SadTalker is the chosen provider, catch obvious-bad inputs
        # (too small for the face cropper, broken header, missing
        # local_path) BEFORE spending GPU cycles. The heavy face-
        # landmark check still happens inside SadTalker; we just
        # short-circuit the inputs we know have zero chance of
        # producing a valid talking head.
        precheck = _precheck_face_image(img, payload)
        if precheck is not None:
            return precheck

        # Phase 10B — when SADTALKER_BASE_URL is set, the light backend
        # proxies the heavy call to the model-sadtalker GPU wrapper over
        # HTTP. The backend image stays torch-free; all readiness
        # checking + inference lives in the wrapper. Bypass the
        # in-process inspect_status (which would always report
        # runtime_missing in the light image) and route directly.
        if os.environ.get("SADTALKER_BASE_URL", "").strip():
            return await _run_sadtalker_via_wrapper(
                session=session,
                payload=payload,
                img=img,
                aud=aud,
            )

        status_info = provider.inspect_status()

        # Not ready (or gate off) → translate without ever invoking
        # ``generate()``. This is the Phase 7B path; Phase 7D inherits
        # the same translator unchanged.
        if status_info["status"] != "ready":
            return _sadtalker_result_from_status(
                status=status_info["status"],
                details=status_info["details"],
                provider_id=payload.provider_id,
                model_id=payload.model_id,
                job_id=payload.job_id,
                image_artifact_id=payload.image_artifact_id,
                audio_artifact_id=payload.audio_artifact_id,
                edit_plan_artifact_id=payload.edit_plan_artifact_id,
                target_duration_seconds=payload.target_duration_seconds,
                img_dims=(img.width, img.height),
                audio_duration_seconds=aud.duration_seconds,
            )

        # Phase 7D — every gate satisfied. Actually run.
        return await _run_sadtalker_and_register(
            provider=provider,
            session=session,
            payload=payload,
            img=img,
            aud=aud,
        )

    # ``musetalk`` / ``wav2lip`` remain Phase 3A placeholders: contract
    # echoed back, no inference attempted. They join sadtalker's
    # treatment in a later phase.
    return VideoGenerationResult(
        status="not_implemented",
        provider_id=payload.provider_id,
        model_id=payload.model_id,
        job_id=payload.job_id,
        error_code="provider_not_implemented",
        message=(
            f"video provider {payload.provider_id!r} is a Phase 3A stub; "
            "real inference + GPU integration land in a later phase. "
            "Inputs validated; no MP4 produced."
        ),
        metadata={
            "image_artifact_id": str(payload.image_artifact_id),
            "audio_artifact_id": str(payload.audio_artifact_id),
            "edit_plan_artifact_id": (
                str(payload.edit_plan_artifact_id)
                if payload.edit_plan_artifact_id is not None
                else None
            ),
            "target_duration_seconds": payload.target_duration_seconds,
            "image_dims": [img.width, img.height] if img.width else None,
            "audio_duration_seconds": aud.duration_seconds,
        },
    )


# ---------------------------------------------------------------------------
# Phase 7D — real inference + artifact registration
# ---------------------------------------------------------------------------


def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _artifacts_root() -> Path:
    """Honour ARTIFACTS_LOCAL_ROOT env override (set in the Docker
    compose files) before falling back to ``settings.artifacts_local_root``."""
    return Path(os.environ.get("ARTIFACTS_LOCAL_ROOT") or settings.artifacts_local_root)


async def _run_sadtalker_and_register(
    *,
    provider,
    session: AsyncSession,
    payload: "VideoGenerationRequest",
    img: Artifact,
    aud: Artifact,
) -> "VideoGenerationResult":
    """All seven gates have passed at the provider level. Call
    ``provider.generate()``, register the resulting MP4 as a video
    artifact, and return ``status="completed"``.

    On categorised provider failure (``runtime_missing`` /
    ``generation_failed`` / etc.), translate back through the Phase 7B
    helper so the response shape stays identical to the no-real-inference
    paths.
    """
    if img.local_path is None or aud.local_path is None:
        return VideoGenerationResult(
            status="missing_inputs",
            provider_id=payload.provider_id,
            model_id=payload.model_id,
            job_id=payload.job_id,
            error_code="missing_local_path",
            message=(
                "Image / audio artifact has no local_path; SadTalker "
                "requires both to be readable from disk."
            ),
        )

    out_dir = _artifacts_root() / "video" / str(payload.job_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    # When sadtalker runs out-of-process (Phase 10B wrapper, uid 10002),
    # the wrapper needs to drop the MP4 into this per-job dir. Widen
    # perms so cross-uid writes succeed regardless of who mkdir'd it.
    # Harmless when the in-process path runs (single uid).
    try:
        out_dir.chmod(0o777)
    except OSError:
        pass

    result = provider.generate(
        image_path=img.local_path,
        audio_path=aud.local_path,
        output_dir=str(out_dir),
        target_duration_seconds=payload.target_duration_seconds,
        model_id=payload.model_id,
    )

    if result.get("status") != "completed":
        # Translate categorised failures via the Phase 7B helper so the
        # response shape is identical to the no-real-inference paths.
        return _sadtalker_result_from_status(
            status=result.get("status", "failed"),
            details=result.get("details", {}),
            provider_id=payload.provider_id,
            model_id=payload.model_id,
            job_id=payload.job_id,
            image_artifact_id=payload.image_artifact_id,
            audio_artifact_id=payload.audio_artifact_id,
            edit_plan_artifact_id=payload.edit_plan_artifact_id,
            target_duration_seconds=payload.target_duration_seconds,
            img_dims=(img.width, img.height),
            audio_duration_seconds=aud.duration_seconds,
        )

    # ----- Success: register the video artifact -----
    output_path = Path(result["output_path"])
    if not output_path.is_file():
        return VideoGenerationResult(
            status="failed",
            provider_id=payload.provider_id,
            model_id=payload.model_id,
            job_id=payload.job_id,
            error_code="video_generation_failed",
            message=(
                f"SadTalker reported success but {output_path} is not "
                "on disk; refusing to register a phantom artifact."
            ),
        )
    size_bytes = output_path.stat().st_size
    checksum = _sha256_of_file(output_path)
    metadata_json = {
        "phase": "phase7d_sadtalker_real_inference",
        "provider_id": "sadtalker",
        "model_id": payload.model_id,
        "target_duration_seconds": payload.target_duration_seconds,
        "image_artifact_id": str(payload.image_artifact_id),
        "audio_artifact_id": str(payload.audio_artifact_id),
        "edit_plan_artifact_id": (
            str(payload.edit_plan_artifact_id)
            if payload.edit_plan_artifact_id is not None
            else None
        ),
        "sadtalker_details": result.get("details", {}),
    }
    artifact = await artifact_service.register_artifact(
        session,
        job_id=payload.job_id,
        artifact_type=ArtifactType.video.value,
        uri=output_path.as_uri(),
        local_path=str(output_path),
        mime_type="video/mp4",
        checksum_sha256=checksum,
        size_bytes=size_bytes,
        duration_seconds=result.get("duration_seconds"),
        width=result.get("width"),
        height=result.get("height"),
        metadata_json=metadata_json,
    )
    return VideoGenerationResult(
        status="completed",
        provider_id=payload.provider_id,
        model_id=payload.model_id,
        job_id=payload.job_id,
        output_video_artifact_id=artifact.id,
        message="SadTalker inference completed.",
        metadata={
            "image_artifact_id": str(payload.image_artifact_id),
            "audio_artifact_id": str(payload.audio_artifact_id),
            "edit_plan_artifact_id": (
                str(payload.edit_plan_artifact_id)
                if payload.edit_plan_artifact_id is not None
                else None
            ),
            "target_duration_seconds": payload.target_duration_seconds,
            "image_dims": [img.width, img.height] if img.width else None,
            "audio_duration_seconds": aud.duration_seconds,
            "video_uri": output_path.as_uri(),
            "video_size_bytes": size_bytes,
            "video_checksum_sha256": checksum,
        },
    )


# ---------------------------------------------------------------------------
# Phase 10B — HTTP proxy to the model-sadtalker GPU wrapper
# ---------------------------------------------------------------------------


_SADTALKER_WRAPPER_TO_BACKEND = {
    "runtime_missing": "video_runtime_missing",
    "gpu_unavailable": "video_gpu_missing",
    "assets_missing": "video_assets_missing",
    "generation_failed": "video_generation_failed",
}


async def _run_sadtalker_via_wrapper(
    *,
    session: AsyncSession,
    payload: "VideoGenerationRequest",
    img: Artifact,
    aud: Artifact,
) -> "VideoGenerationResult":
    """Phase 10B: POST to the ``model-sadtalker`` HTTP wrapper. The
    backend keeps its in-process torch-free invariant; the wrapper does
    the CUDA work and writes the MP4 onto the shared artifacts volume.

    On wrapper success: register the MP4 as an ``ArtifactType.video``
    row exactly like the in-process path. On categorised wrapper
    failure: translate the wrapper's ``status``/``error_code`` into the
    same Phase 7B vocabulary the in-process path uses.
    """
    import json
    import urllib.error
    import urllib.request

    if img.local_path is None or aud.local_path is None:
        return VideoGenerationResult(
            status="missing_inputs",
            provider_id=payload.provider_id,
            model_id=payload.model_id,
            job_id=payload.job_id,
            error_code="missing_local_path",
            message=(
                "Image / audio artifact has no local_path; SadTalker "
                "wrapper needs both readable from the shared volume."
            ),
        )

    base_url = os.environ.get("SADTALKER_BASE_URL", "").strip()
    if not base_url:
        return VideoGenerationResult(
            status="not_configured",
            provider_id=payload.provider_id,
            model_id=payload.model_id,
            job_id=payload.job_id,
            error_code="video_provider_not_configured",
            message=(
                "SADTALKER_BASE_URL is unset; backend cannot reach the "
                "model-sadtalker wrapper. Start it with "
                "`make docker-sadtalker-up`."
            ),
        )

    # Pre-compute the output path on the shared artifacts volume so the
    # wrapper writes where the backend can later checksum + register.
    # The wrapper container runs as a different non-root uid (10002) than
    # the backend (1000); both must be able to create + write files in
    # this per-job subdir. We widen perms after mkdir so the wrapper's
    # shutil.move() can land the MP4 (the umask makes the default 0755).
    out_dir = _artifacts_root() / "video" / str(payload.job_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        out_dir.chmod(0o777)
    except OSError:
        pass
    out_name = f"sadtalker_{uuid.uuid4().hex}.mp4"
    out_path = out_dir / out_name

    body = {
        "image_path": img.local_path,
        "audio_path": aud.local_path,
        "output_path": str(out_path),
        "target_duration_seconds": payload.target_duration_seconds,
        "model_id": payload.model_id,
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
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )

    timeout = int(os.environ.get("SADTALKER_HTTP_TIMEOUT", "1200"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload_bytes = resp.read()
            http_code = resp.status
    except urllib.error.HTTPError as exc:
        err_text = exc.read().decode("utf-8", errors="replace")[:500]
        return VideoGenerationResult(
            status="failed",
            provider_id=payload.provider_id,
            model_id=payload.model_id,
            job_id=payload.job_id,
            error_code="video_generation_failed",
            message=f"SadTalker wrapper HTTP {exc.code}: {err_text}",
        )
    except urllib.error.URLError as exc:
        return VideoGenerationResult(
            status="not_configured",
            provider_id=payload.provider_id,
            model_id=payload.model_id,
            job_id=payload.job_id,
            error_code="video_runtime_missing",
            message=(
                f"SadTalker wrapper unreachable at {base_url!r}: "
                f"{type(exc).__name__}: {getattr(exc, 'reason', exc)}"
            ),
        )

    try:
        wrapper = json.loads(payload_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return VideoGenerationResult(
            status="failed",
            provider_id=payload.provider_id,
            model_id=payload.model_id,
            job_id=payload.job_id,
            error_code="video_generation_failed",
            message=f"SadTalker wrapper returned malformed JSON: {exc}",
        )

    wrapper_status = wrapper.get("status")
    if wrapper_status != "completed":
        # Categorise + return; clean any partial MP4 the wrapper may
        # have created on a hard exit.
        try:
            if out_path.is_file() and out_path.stat().st_size == 0:
                out_path.unlink(missing_ok=True)
        except OSError:
            pass
        be_code = _SADTALKER_WRAPPER_TO_BACKEND.get(
            str(wrapper_status), "video_generation_failed"
        )
        return VideoGenerationResult(
            status="failed" if wrapper_status == "generation_failed" else "not_configured",
            provider_id=payload.provider_id,
            model_id=payload.model_id,
            job_id=payload.job_id,
            error_code=be_code,
            message=str(wrapper.get("message") or wrapper.get("error_code") or wrapper_status),
            metadata={"wrapper": wrapper, "http_code": http_code},
        )

    # ----- Wrapper success: validate + register the artifact -----
    final_path = Path(wrapper.get("output_path") or out_path)
    if not final_path.is_file() or final_path.stat().st_size == 0:
        return VideoGenerationResult(
            status="failed",
            provider_id=payload.provider_id,
            model_id=payload.model_id,
            job_id=payload.job_id,
            error_code="video_generation_failed",
            message=(
                f"SadTalker wrapper reported completed but {final_path} is "
                "missing/empty. Refusing to register a phantom artifact."
            ),
        )

    size_bytes = final_path.stat().st_size
    checksum = _sha256_of_file(final_path)
    metadata_json = {
        "phase": "phase10b_sadtalker_via_wrapper",
        "provider_id": "sadtalker",
        "model_id": payload.model_id,
        "target_duration_seconds": payload.target_duration_seconds,
        "image_artifact_id": str(payload.image_artifact_id),
        "audio_artifact_id": str(payload.audio_artifact_id),
        "edit_plan_artifact_id": (
            str(payload.edit_plan_artifact_id)
            if payload.edit_plan_artifact_id is not None
            else None
        ),
        "wrapper_base_url": base_url,
        "wrapper_http_code": http_code,
        "wrapper_metadata": wrapper.get("metadata") or {},
    }
    artifact = await artifact_service.register_artifact(
        session,
        job_id=payload.job_id,
        artifact_type=ArtifactType.video.value,
        uri=final_path.as_uri(),
        local_path=str(final_path),
        mime_type="video/mp4",
        checksum_sha256=checksum,
        size_bytes=size_bytes,
        duration_seconds=wrapper.get("duration_seconds"),
        width=wrapper.get("width"),
        height=wrapper.get("height"),
        metadata_json=metadata_json,
    )
    return VideoGenerationResult(
        status="completed",
        provider_id=payload.provider_id,
        model_id=payload.model_id,
        job_id=payload.job_id,
        output_video_artifact_id=artifact.id,
        message="SadTalker (via model-sadtalker wrapper) completed.",
        metadata={
            "image_artifact_id": str(payload.image_artifact_id),
            "audio_artifact_id": str(payload.audio_artifact_id),
            "edit_plan_artifact_id": (
                str(payload.edit_plan_artifact_id)
                if payload.edit_plan_artifact_id is not None
                else None
            ),
            "target_duration_seconds": payload.target_duration_seconds,
            "image_dims": [img.width, img.height] if img.width else None,
            "audio_duration_seconds": aud.duration_seconds,
            "video_uri": final_path.as_uri(),
            "video_size_bytes": size_bytes,
            "video_checksum_sha256": checksum,
            "wrapper_base_url": base_url,
            "wrapper_metadata": wrapper.get("metadata") or {},
        },
    )

