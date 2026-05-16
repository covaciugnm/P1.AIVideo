"""Phase 4A-2 upload + from-inputs API.

Two routers live in this module:

- ``uploads_router`` (``/api/v1/uploads``) — three endpoints that accept
  text / WAV audio / image input. Each one validates structure and
  size, persists the file (or, for text, a small JSON sidecar) under a
  configured upload root, computes a SHA-256, and registers an
  "intake" ``Artifact`` row (``job_id`` is NULL — the artifact is
  linked to a job later via ``POST /api/v1/jobs/from-inputs``).

- ``jobs_v1_router`` (``/api/v1/jobs``) — currently just
  ``POST /from-inputs``, which dereferences uploaded artifact ids back
  into the ``JobCreateRequest`` shape, then funnels the request through
  ``job_service.create_job`` so every existing validator
  (synthetic_person_confirmed, consent_confirmed, AudioRef/ImageRef
  path-safety, etc.) still applies.

No binary content ever appears in a response body. No external upload.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.audio_validation import validate_and_inspect_wav
from common.enums import ArtifactType
from common.image_validation import validate_and_inspect_image
from common.schemas import AudioRef, ImageRef

from app.core.config import settings
from app.core.deps import get_db_session
from app.models.artifact import Artifact
from app.schemas.job import JobCreateRequest, JobResponse
from app.schemas.uploads import (
    JobFromInputsRequest,
    UploadAudioResponse,
    UploadImageResponse,
    UploadTextRequest,
    UploadTextResponse,
)
from app.services import artifact_service, audio_conversion, job_service, upload_service


uploads_router = APIRouter(prefix="/api/v1/uploads", tags=["uploads"])
jobs_v1_router = APIRouter(prefix="/api/v1/jobs", tags=["jobs-v1"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_WAV_EXTENSIONS = {".wav"}
_WAV_MIME_TYPES = {"audio/wav", "audio/x-wav", "audio/wave"}

# Phase 4F: broader accept list. Non-WAV inputs are transcoded to a
# normalized PCM WAV by ffmpeg when available; otherwise stored as-is
# with a ``needs_conversion`` flag.
_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}
_AUDIO_MIME_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/x-m4a",
    "audio/aac",
    "audio/flac",
    "audio/x-flac",
    "audio/ogg",
    "audio/vorbis",
}
_AUDIO_MIME_BY_EXT = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
}

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}
_IMAGE_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _max_audio_size() -> int:
    import os

    raw = os.environ.get("AUDIO_MAX_FILE_SIZE_BYTES")
    if raw:
        try:
            v = int(raw)
            if v > 0:
                return v
        except ValueError:
            pass
    return settings.audio_max_file_size_bytes


def _max_image_size() -> int:
    import os

    raw = os.environ.get("IMAGE_MAX_FILE_SIZE_BYTES")
    if raw:
        try:
            v = int(raw)
            if v > 0:
                return v
        except ValueError:
            pass
    return settings.image_max_file_size_bytes


def _max_script_chars() -> int:
    import os

    raw = os.environ.get("SCRIPT_TEXT_MAX_CHARS")
    if raw:
        try:
            v = int(raw)
            if v > 0:
                return v
        except ValueError:
            pass
    return settings.script_text_max_chars


def _safe_extension(filename: str | None, allowed: set[str]) -> str:
    if not filename:
        raise HTTPException(status_code=400, detail="missing filename")
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported extension {suffix!r}; allowed: {sorted(allowed)}",
        )
    return suffix


# ---------------------------------------------------------------------------
# POST /api/v1/uploads/text
# ---------------------------------------------------------------------------


@uploads_router.post("/text", response_model=UploadTextResponse, status_code=201)
async def upload_text(
    payload: UploadTextRequest,
    session: AsyncSession = Depends(get_db_session),
) -> UploadTextResponse:
    text = payload.script_text
    if len(text) > _max_script_chars():
        raise HTTPException(
            status_code=413,
            detail=f"script_text exceeds SCRIPT_TEXT_MAX_CHARS={_max_script_chars()}",
        )

    root = upload_service.get_upload_root("UPLOAD_TEXT_ROOT", settings.upload_text_root)
    filename = upload_service.safe_unique_filename(".json")
    dest = root / filename

    record = {
        "title": payload.title,
        "script_text": text,
        "language": payload.language,
        "tone": payload.tone,
        "target_duration_seconds": payload.target_duration_seconds,
    }
    serialized = json.dumps(record, sort_keys=True, ensure_ascii=False).encode("utf-8")
    dest.write_bytes(serialized)

    checksum = hashlib.sha256(serialized).hexdigest()
    metadata_json: dict[str, Any] = {
        "phase": "phase4a2_upload_text",
        "source": "upload_text",
        "script_text": text,
        "title": payload.title,
        "language": payload.language,
        "tone": payload.tone,
        "target_duration_seconds": payload.target_duration_seconds,
    }

    artifact = await artifact_service.register_artifact(
        session,
        artifact_type=ArtifactType.script.value,
        uri=dest.as_uri(),
        local_path=str(dest),
        mime_type="application/json",
        checksum_sha256=checksum,
        size_bytes=len(serialized),
        metadata_json=metadata_json,
    )

    script_ref = {
        "type": "artifact",
        "artifact_id": str(artifact.id),
        "artifact_type": artifact.artifact_type,
        "uri": artifact.uri,
        "checksum_sha256": artifact.checksum_sha256,
    }
    return UploadTextResponse(
        artifact_id=artifact.id,
        artifact_type=artifact.artifact_type,
        uri=artifact.uri,
        mime_type=artifact.mime_type,
        checksum_sha256=artifact.checksum_sha256,
        size_bytes=artifact.size_bytes,
        script_ref=script_ref,
        metadata_summary=dict(artifact.metadata_json or {}),
    )


# ---------------------------------------------------------------------------
# POST /api/v1/uploads/audio
# ---------------------------------------------------------------------------


@uploads_router.post("/audio", response_model=UploadAudioResponse, status_code=201)
async def upload_audio(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
) -> UploadAudioResponse:
    suffix = _safe_extension(file.filename, _AUDIO_EXTENSIONS)
    expected_mime = _AUDIO_MIME_BY_EXT[suffix]
    declared_mime = (file.content_type or "").lower() or expected_mime
    if declared_mime not in _AUDIO_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported audio mime_type {declared_mime!r}",
        )

    root = upload_service.get_upload_root("UPLOAD_AUDIO_ROOT", settings.upload_audio_root)
    dest = root / upload_service.safe_unique_filename(suffix)
    max_size = _max_audio_size()
    bytes_written = await upload_service.save_streaming_upload(file, dest, max_size=max_size)

    is_wav = suffix == ".wav"
    converted_path: Path | None = None

    if is_wav:
        try:
            meta = validate_and_inspect_wav(
                dest, mime_type="audio/wav", max_size_bytes=max_size
            )
        except ValueError as exc:
            dest.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        served_path = dest
        served_mime = "audio/wav"
        needs_conversion = False
        ffmpeg_available = audio_conversion.has_ffmpeg()
    else:
        # Non-WAV: convert to PCM WAV alongside the original if ffmpeg is
        # available. The frontend will reference the converted artifact as
        # the canonical pipeline audio; the original is kept for audit.
        ffmpeg_available = audio_conversion.has_ffmpeg()
        if not ffmpeg_available:
            # Compute basic metadata from the original; no transcode possible.
            original_size = dest.stat().st_size
            served_path = dest
            served_mime = expected_mime
            needs_conversion = True
            # We can't safely invoke the WAV validator on a non-WAV stream;
            # synthesise a minimal AudioMetadata-like view.
            import hashlib

            h = hashlib.sha256()
            with dest.open("rb") as f:
                for chunk in iter(lambda: f.read(64 * 1024), b""):
                    h.update(chunk)

            class _Meta:
                sample_rate = 0
                channels = 0
                duration_seconds = 0.0
                checksum_sha256 = h.hexdigest()
                size_bytes = original_size

            meta = _Meta()
        else:
            converted_path = dest.with_suffix(".converted.wav")
            try:
                conv = audio_conversion.convert_to_wav(dest, converted_path)
            except audio_conversion.AudioConversionError as exc:
                dest.unlink(missing_ok=True)
                converted_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=400,
                    detail=f"audio_conversion_failed: {exc}",
                ) from exc
            # Validate the converted WAV with the existing Phase 3D
            # validator so downstream invariants (header sanity, size cap)
            # still hold.
            try:
                meta = validate_and_inspect_wav(
                    converted_path,
                    mime_type="audio/wav",
                    max_size_bytes=max_size,
                )
            except ValueError as exc:
                dest.unlink(missing_ok=True)
                converted_path.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            served_path = converted_path
            served_mime = "audio/wav"
            needs_conversion = False

    metadata_json: dict[str, Any] = {
        "phase": "phase4f_upload_audio",
        "source": "upload_audio",
        "mime_type": served_mime,
        "declared_mime_type": declared_mime,
        "original_extension": suffix,
        "original_size_bytes": bytes_written,
        "needs_conversion": needs_conversion,
        "ffmpeg_available": ffmpeg_available,
        "sample_rate": meta.sample_rate,
        "channels": meta.channels,
        "duration_seconds": meta.duration_seconds,
    }
    if converted_path is not None:
        metadata_json["original_local_path"] = str(dest)
        metadata_json["converted_to_wav"] = True

    artifact = await artifact_service.register_artifact(
        session,
        artifact_type=ArtifactType.audio.value,
        uri=served_path.as_uri(),
        local_path=str(served_path),
        mime_type=served_mime,
        checksum_sha256=meta.checksum_sha256,
        size_bytes=meta.size_bytes,
        duration_seconds=meta.duration_seconds,
        sample_rate=meta.sample_rate,
        channels=meta.channels,
        metadata_json=metadata_json,
    )

    audio_ref = {
        "type": "local_path",
        "path": str(served_path),
        "mime_type": served_mime,
        "duration_seconds": meta.duration_seconds,
        "checksum": meta.checksum_sha256,
        "artifact_id": str(artifact.id),
    }
    return UploadAudioResponse(
        artifact_id=artifact.id,
        artifact_type=artifact.artifact_type,
        uri=artifact.uri,
        local_path=str(served_path),
        mime_type=served_mime,
        checksum_sha256=meta.checksum_sha256,
        size_bytes=meta.size_bytes,
        duration_seconds=meta.duration_seconds,
        sample_rate=meta.sample_rate,
        channels=meta.channels,
        audio_ref=audio_ref,
        metadata_summary=dict(artifact.metadata_json or {}),
    )


# ---------------------------------------------------------------------------
# POST /api/v1/uploads/image
# ---------------------------------------------------------------------------


@uploads_router.post("/image", response_model=UploadImageResponse, status_code=201)
async def upload_image(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
) -> UploadImageResponse:
    suffix = _safe_extension(file.filename, _IMAGE_EXTENSIONS)
    expected_mime = _IMAGE_MIME_BY_EXT[suffix]
    declared_mime = (file.content_type or "").lower() or expected_mime
    if declared_mime not in _IMAGE_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported image mime_type {declared_mime!r}",
        )
    # The extension is authoritative for the inspector — operators sometimes
    # mis-set Content-Type. We use the extension-derived mime.
    inspect_mime = expected_mime

    root = upload_service.get_upload_root("UPLOAD_IMAGE_ROOT", settings.upload_image_root)
    dest = root / upload_service.safe_unique_filename(suffix)
    max_size = _max_image_size()
    bytes_written = await upload_service.save_streaming_upload(file, dest, max_size=max_size)

    try:
        meta = validate_and_inspect_image(
            dest, mime_type=inspect_mime, max_size_bytes=max_size
        )
    except ValueError as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    metadata_json: dict[str, Any] = {
        "phase": "phase4a2_upload_image",
        "source": "upload_image",
        "mime_type": inspect_mime,
        "declared_mime_type": declared_mime,
        "format": meta.format,
        "width": meta.width,
        "height": meta.height,
        "bytes_written": bytes_written,
    }

    artifact = await artifact_service.register_artifact(
        session,
        artifact_type=ArtifactType.image.value,
        uri=dest.as_uri(),
        local_path=str(dest),
        mime_type=inspect_mime,
        checksum_sha256=meta.checksum_sha256,
        size_bytes=meta.size_bytes,
        width=meta.width,
        height=meta.height,
        metadata_json=metadata_json,
    )

    image_ref = {
        "type": "local_path",
        "path": str(dest),
        "mime_type": inspect_mime,
        "checksum": meta.checksum_sha256,
        "artifact_id": str(artifact.id),
    }
    return UploadImageResponse(
        artifact_id=artifact.id,
        artifact_type=artifact.artifact_type,
        uri=artifact.uri,
        local_path=str(dest),
        mime_type=inspect_mime,
        checksum_sha256=meta.checksum_sha256,
        size_bytes=meta.size_bytes,
        width=meta.width,
        height=meta.height,
        image_ref=image_ref,
        metadata_summary=dict(artifact.metadata_json or {}),
    )


# ---------------------------------------------------------------------------
# POST /api/v1/jobs/from-inputs
# ---------------------------------------------------------------------------


async def _load_artifact_by_id(
    session: AsyncSession, artifact_id: uuid.UUID
) -> Artifact:
    result = await session.execute(
        select(Artifact).where(Artifact.id == artifact_id)
    )
    art = result.scalar_one_or_none()
    if art is None:
        raise HTTPException(
            status_code=400, detail=f"artifact {artifact_id} not found"
        )
    return art


@jobs_v1_router.post("/from-inputs", response_model=JobResponse, status_code=201)
async def create_job_from_inputs(
    payload: JobFromInputsRequest,
    session: AsyncSession = Depends(get_db_session),
) -> JobResponse:
    # Resolve script_text: inline first, then artifact lookup.
    script_text: str | None = payload.script_text
    if script_text is None and payload.script_artifact_id is not None:
        script_art = await _load_artifact_by_id(session, payload.script_artifact_id)
        if script_art.artifact_type != ArtifactType.script.value:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"artifact {payload.script_artifact_id} is "
                    f"{script_art.artifact_type!r}, expected script"
                ),
            )
        md = script_art.metadata_json or {}
        candidate = md.get("script_text")
        if not isinstance(candidate, str) or not candidate.strip():
            raise HTTPException(
                status_code=400,
                detail=(
                    f"script artifact {payload.script_artifact_id} is missing "
                    "metadata_json['script_text']"
                ),
            )
        script_text = candidate

    # Build AudioRef from uploaded artifact if provided_audio.
    audio_ref: AudioRef | None = None
    if payload.voice_mode == "provided_audio":
        if payload.audio_artifact_id is None:
            # Guarded at schema time too; defensive double-check.
            raise HTTPException(
                status_code=400,
                detail="audio_artifact_id is required for voice_mode='provided_audio'",
            )
        audio_art = await _load_artifact_by_id(session, payload.audio_artifact_id)
        if audio_art.artifact_type != ArtifactType.audio.value:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"artifact {payload.audio_artifact_id} is "
                    f"{audio_art.artifact_type!r}, expected audio"
                ),
            )
        if not audio_art.local_path:
            raise HTTPException(
                status_code=400,
                detail="audio artifact has no local_path",
            )
        # AudioRef will re-validate path safety against PROVIDED_AUDIO_ALLOWED_ROOTS.
        try:
            audio_ref = AudioRef(
                type="local_path",
                path=audio_art.local_path,
                mime_type=audio_art.mime_type or "audio/wav",  # type: ignore[arg-type]
                duration_seconds=audio_art.duration_seconds,
                checksum=audio_art.checksum_sha256,
                consent_confirmed=payload.audio_consent_confirmed,
                synthetic_or_owned_voice=payload.audio_synthetic_or_owned,
            )
        except Exception as exc:  # ValidationError / ValueError
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Build ImageRef from uploaded artifact if provided_image.
    image_ref: ImageRef | None = None
    if payload.face_mode == "provided_image":
        if payload.image_artifact_id is None:
            raise HTTPException(
                status_code=400,
                detail="image_artifact_id is required for face_mode='provided_image'",
            )
        image_art = await _load_artifact_by_id(session, payload.image_artifact_id)
        if image_art.artifact_type != ArtifactType.image.value:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"artifact {payload.image_artifact_id} is "
                    f"{image_art.artifact_type!r}, expected image"
                ),
            )
        if not image_art.local_path:
            raise HTTPException(
                status_code=400,
                detail="image artifact has no local_path",
            )
        try:
            image_ref = ImageRef(
                type="local_path",
                path=image_art.local_path,
                mime_type=image_art.mime_type or "image/png",  # type: ignore[arg-type]
                checksum=image_art.checksum_sha256,
                consent_confirmed=payload.image_consent_confirmed,
                synthetic_person_confirmed=payload.image_synthetic_person_confirmed,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Funnel through the existing JobCreateRequest path so every
    # validator (synthetic_person_confirmed, consent_confirmed,
    # AudioRef/ImageRef path-safety) re-runs.
    try:
        create_req = JobCreateRequest(
            brief=payload.brief,
            synthetic_person_confirmed=payload.synthetic_person_confirmed,
            consent_confirmed=payload.consent_confirmed,
            target_duration_seconds=payload.target_duration_seconds,
            watermark_required=payload.watermark_required,
            c2pa_required=payload.c2pa_required,
            voice_mode=payload.voice_mode,
            script_text=script_text,
            audio_ref=audio_ref,
            face_mode=payload.face_mode,
            image_ref=image_ref,
            # Phase 8E — forward provider_selection so the upload-intake
            # path persists the same operator choices the /jobs path does.
            provider_selection=payload.provider_selection,
            # Phase 11A — forward language + subtitle metadata.
            video_language=payload.video_language,
            subtitle_enabled=payload.subtitle_enabled,
            subtitle_languages=payload.subtitle_languages,
            subtitle_format=payload.subtitle_format,
            subtitle_burn_in=payload.subtitle_burn_in,
            transcript_language=payload.transcript_language,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    job = await job_service.create_job(session, create_req)

    # Phase 11A — if subtitles are enabled and we have script_text, drop
    # one sidecar SRT/VTT artifact per requested language. Best-effort:
    # the subtitle service rounds-down to "approximate" timing because
    # we don't have forced alignment in light dev.
    if create_req.subtitle_enabled and script_text:
        from app.services import subtitle_service

        try:
            await subtitle_service.generate_subtitle_artifacts(
                session,
                job_id=job.id,
                script_text=script_text,
                languages=create_req.subtitle_languages or [create_req.video_language],
                fmt=create_req.subtitle_format,
                target_duration_seconds=create_req.target_duration_seconds,
                burn_in_requested=create_req.subtitle_burn_in,
            )
            await session.commit()
        except Exception:  # noqa: BLE001 — defensive
            # Subtitle generation must never block job creation. Swallow
            # and continue; the operator can re-run via a future endpoint.
            await session.rollback()

    return JobResponse.model_validate(job)
