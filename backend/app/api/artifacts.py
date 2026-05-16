"""Artifact content serving.

GET /api/v1/artifacts/{artifact_id}/content returns the binary file
behind an artifact row, with strict guards:

- Artifact must exist in the DB.
- Artifact type must be in the serve-allowed list (audio, image,
  script, video).
- ``local_path`` must resolve to a real file.
- Resolved path must live under one of the configured allowed roots
  (uploads + provided-asset roots + artifacts root). Defends against
  any DB row that somehow points outside.
- Path traversal symbols rejected at validation time.
- Optional ``?download=true`` switches Content-Disposition from
  ``inline`` to ``attachment`` and picks a safe filename based on the
  artifact's mime type.

No path is ever returned to the client. The response is a streaming
file with the artifact's recorded ``mime_type``.

Phase 8A adds ``video`` to the allow-list + the artifacts root to the
allowed-roots set (where Phase 7D registers generated MP4s) + the
optional download query param.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_db_session
from app.models.artifact import Artifact

router = APIRouter(prefix="/api/v1/artifacts", tags=["artifacts"])


# Phase 8A: ``video`` joins the serve allow-list.
# Phase 8B: ``final_export`` joins too, but only the real-MP4 variant
# created by ``/api/v1/export/finalize`` — JSON manifests still don't
# have a ``local_path`` so they 404 naturally without leaking 415 vs
# 404 information about which final_export rows exist.
# ``edit_plan`` / ``metadata`` stay out — they're JSON-only artifacts
# operators never scrub through in the browser.
_SERVE_ALLOWED_TYPES = frozenset(
    {"audio", "image", "script", "video", "final_export", "subtitle"}
)


# Mapping from artifact mime type → safe download filename suffix. Used
# only when ``?download=true`` is passed and the artifact has no
# operator-supplied filename. Kept narrow so a future mime gets a
# documented entry rather than a silent ``.bin`` fallback.
_MIME_TO_DOWNLOAD_SUFFIX: dict[str, str] = {
    "audio/wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/aac": ".aac",
    "audio/flac": ".flac",
    "audio/ogg": ".ogg",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "text/plain": ".txt",
    "text/vtt": ".vtt",
    "application/x-subrip": ".srt",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
}


def _split_roots(value: str) -> list[Path]:
    return [Path(p).resolve(strict=False) for p in value.split(",") if p.strip()]


def _allowed_roots() -> list[Path]:
    """Re-read on each call so tests using monkeypatch.setenv work."""
    raw_audio = os.environ.get("PROVIDED_AUDIO_ALLOWED_ROOTS", "")
    raw_image = os.environ.get("PROVIDED_IMAGE_ALLOWED_ROOTS", "")
    out: list[Path] = []
    out.extend(_split_roots(raw_audio))
    out.extend(_split_roots(raw_image))
    # Upload roots (Phase 4A-2) — operator-supplied files land here.
    for env_name, default in (
        ("UPLOAD_AUDIO_ROOT", settings.upload_audio_root),
        ("UPLOAD_IMAGE_ROOT", settings.upload_image_root),
        ("UPLOAD_TEXT_ROOT", settings.upload_text_root),
    ):
        raw = os.environ.get(env_name, default)
        out.append(Path(raw).resolve(strict=False))
    # Phase 11A — subtitle sidecar artifacts live under
    # ``$ARTIFACTS_LOCAL_ROOT/subtitles/...``. The artifacts root is
    # already added below, but we resolve again here to be explicit so
    # the path-safety check accepts subtitle files even if a future
    # phase moves them under a separate env var.
    out.append(
        Path(
            os.environ.get("SUBTITLES_LOCAL_ROOT")
            or os.environ.get("ARTIFACTS_LOCAL_ROOT")
            or settings.artifacts_local_root
        ).resolve(strict=False)
    )
    # Phase 8A: the artifacts root, where Phase 7D's video files (and
    # Phase 8B's final-export MP4s) land. Honour the env override the
    # compose files set.
    artifacts_raw = os.environ.get(
        "ARTIFACTS_LOCAL_ROOT", settings.artifacts_local_root
    )
    out.append(Path(artifacts_raw).resolve(strict=False))
    return out


def _is_under_allowed_root(p: Path) -> bool:
    for root in _allowed_roots():
        try:
            p.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _download_filename(artifact: Artifact) -> str:
    """Pick a safe filename for the ``Content-Disposition: attachment``
    header. We never echo the raw local_path — that's an operator
    filesystem detail. Stable scheme: ``artifact-<short-uuid><suffix>``."""
    suffix = _MIME_TO_DOWNLOAD_SUFFIX.get(artifact.mime_type or "", ".bin")
    short = str(artifact.id).split("-")[0]
    return f"artifact-{short}{suffix}"


@router.get("/{artifact_id}/content")
async def get_artifact_content(
    artifact_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    download: bool = Query(default=False),
) -> FileResponse:
    result = await session.execute(
        select(Artifact).where(Artifact.id == artifact_id)
    )
    artifact = result.scalar_one_or_none()
    if artifact is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    if artifact.artifact_type not in _SERVE_ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"artifact_type {artifact.artifact_type!r} is not serveable",
        )
    if not artifact.local_path:
        raise HTTPException(status_code=404, detail="artifact has no local content")

    raw_path = artifact.local_path
    # Reject obvious path-traversal symbols even before resolving.
    if ".." in raw_path.split(os.sep):
        raise HTTPException(status_code=403, detail="unsafe artifact path")
    try:
        resolved = Path(raw_path).resolve(strict=True)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="artifact file missing") from exc
    if not _is_under_allowed_root(resolved):
        raise HTTPException(
            status_code=403, detail="artifact path is outside allowed roots"
        )

    media_type = artifact.mime_type or "application/octet-stream"
    if download:
        filename = _download_filename(artifact)
        disposition = f'attachment; filename="{filename}"'
    else:
        disposition = "inline"
    return FileResponse(
        resolved,
        media_type=media_type,
        headers={
            "Cache-Control": "private, max-age=60",
            "Content-Disposition": disposition,
        },
    )
