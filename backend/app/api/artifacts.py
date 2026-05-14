"""Phase 4F artifact content serving.

GET /api/v1/artifacts/{artifact_id}/content returns the binary file
behind an artifact row, with strict guards:

- Artifact must exist in the DB.
- Artifact type must be in the serve-allowed list (audio, image, script).
- ``local_path`` must resolve to a real file.
- Resolved path must live under one of the configured allowed roots
  (uploads + provided-asset roots from env) — defends against any DB row
  that somehow points outside.
- Path traversal symbols rejected at validation time.

No path is ever returned to the client. The response is a streaming file
with the artifact's recorded ``mime_type``.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_db_session
from app.models.artifact import Artifact

router = APIRouter(prefix="/api/v1/artifacts", tags=["artifacts"])


_SERVE_ALLOWED_TYPES = frozenset({"audio", "image", "script"})


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
    return out


def _is_under_allowed_root(p: Path) -> bool:
    for root in _allowed_roots():
        try:
            p.relative_to(root)
            return True
        except ValueError:
            continue
    return False


@router.get("/{artifact_id}/content")
async def get_artifact_content(
    artifact_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
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
    return FileResponse(
        resolved,
        media_type=media_type,
        headers={
            "Cache-Control": "private, max-age=60",
            "Content-Disposition": "inline",
        },
    )
