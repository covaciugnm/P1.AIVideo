"""/api/v1/characters/* endpoints — Phase 12.

CRUD + lookups + image library + script context. Soft delete is the
default; deleting a character does NOT cascade into the jobs that
referenced it — every job carries a frozen ``character_snapshot`` so
old videos preserve their persona profile.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

logger = logging.getLogger(__name__)
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.schemas.character import (
    CharacterCreateRequest,
    CharacterImageActionResponse,
    CharacterImageGenerateError,
    CharacterImageGenerateRequest,
    CharacterImageListResponse,
    CharacterImageResponse,
    CharacterListResponse,
    CharacterLookupsResponse,
    CharacterResponse,
    CharacterScriptContextResponse,
    CharacterSummary,
    CharacterUpdateRequest,
)
from app.services import (
    character_image_service,
    character_lookups,
    character_script_context,
    character_service,
)
from app.services.image_providers import ProviderUnavailableError

router = APIRouter(prefix="/api/v1/characters", tags=["characters"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _load_character_or_404(session: AsyncSession, character_id: uuid.UUID):
    character = await character_service.get_character(session, character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="character not found")
    return character


# ---------------------------------------------------------------------------
# Lookups (translatable dropdown catalogue)
# ---------------------------------------------------------------------------


@router.get("/lookups", response_model=CharacterLookupsResponse)
async def get_character_lookups() -> CharacterLookupsResponse:
    return character_lookups.build_character_lookups()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.get("", response_model=CharacterListResponse)
async def list_characters(
    include_deleted: bool = False,
    status: str | None = None,
    limit: int = 200,
    session: AsyncSession = Depends(get_db_session),
) -> CharacterListResponse:
    items, total = await character_service.list_characters(
        session,
        include_deleted=include_deleted,
        status=status,
        limit=max(1, min(limit, 500)),
    )
    return CharacterListResponse(items=items, total=total)


@router.post("", response_model=CharacterResponse, status_code=201)
async def create_character(
    request: CharacterCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> CharacterResponse:
    logger.info(
        "characters.create.start name=%r status=%s",
        request.profile.identity.name, request.status,
    )
    row = await character_service.create_character(session, request)
    logger.info(
        "characters.create.done id=%s name=%r",
        row.id, row.profile_json.get("identity", {}).get("name") if row.profile_json else None,
    )
    return await character_service.to_response(session, row)


@router.get("/{character_id}", response_model=CharacterResponse)
async def get_character(
    character_id: uuid.UUID,
    include_deleted: bool = False,
    session: AsyncSession = Depends(get_db_session),
) -> CharacterResponse:
    character = await character_service.get_character(
        session, character_id, include_deleted=include_deleted
    )
    if character is None:
        raise HTTPException(status_code=404, detail="character not found")
    return await character_service.to_response(session, character)


@router.put("/{character_id}", response_model=CharacterResponse)
async def update_character(
    character_id: uuid.UUID,
    request: CharacterUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> CharacterResponse:
    logger.info("characters.update.start id=%s fields=%s", character_id, list(request.model_dump(exclude_none=True).keys()))
    character = await _load_character_or_404(session, character_id)
    character = await character_service.update_character(session, character, request)
    logger.info("characters.update.done id=%s", character.id)
    return await character_service.to_response(session, character)


@router.delete("/{character_id}", response_model=CharacterResponse)
async def delete_character(
    character_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> CharacterResponse:
    logger.info("characters.delete.start id=%s", character_id)
    character = await _load_character_or_404(session, character_id)
    character = await character_service.soft_delete_character(session, character)
    logger.info("characters.delete.done id=%s", character.id)
    return await character_service.to_response(session, character)


# ---------------------------------------------------------------------------
# Script context (Phase D)
# ---------------------------------------------------------------------------


@router.get(
    "/{character_id}/script-context",
    response_model=CharacterScriptContextResponse,
)
async def get_character_script_context(
    character_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> CharacterScriptContextResponse:
    character = await _load_character_or_404(session, character_id)
    from app.schemas.character import CharacterProfile

    profile = CharacterProfile.model_validate(character.profile_json)
    return character_script_context.build_character_script_context(
        profile, character_id=character.id
    )


# ---------------------------------------------------------------------------
# Image library
# ---------------------------------------------------------------------------


@router.get(
    "/{character_id}/images",
    response_model=CharacterImageListResponse,
)
async def list_images(
    character_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> CharacterImageListResponse:
    await _load_character_or_404(session, character_id)
    rows, total = await character_image_service.list_images(session, character_id)
    items = [character_image_service.to_response(r) for r in rows]
    return CharacterImageListResponse(items=items, total=total)


@router.post(
    "/{character_id}/images/generate",
    response_model=CharacterImageResponse,
    status_code=201,
)
async def generate_image(
    character_id: uuid.UUID,
    request: CharacterImageGenerateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> CharacterImageResponse:
    logger.info(
        "characters.image.endpoint.start character_id=%s provider=%s model=%s use_main_ref=%s",
        character_id, request.provider_id, request.model_id, request.use_main_reference,
    )
    character = await _load_character_or_404(session, character_id)
    try:
        row = await character_image_service.generate_image(session, character, request)
    except ProviderUnavailableError as exc:
        logger.warning(
            "characters.image.endpoint.failed character_id=%s code=%s detail=%s",
            character_id, exc.error_code, exc.detail,
        )
        payload = CharacterImageGenerateError(
            error_code=exc.error_code,  # type: ignore[arg-type]
            detail=exc.detail,
            provider_id=request.provider_id,
            fallback=exc.fallback,
        )
        # 422 for validation, 503 for unavailable, 501 for not implemented.
        status_map = {
            "validation_failed": 422,
            "reference_image_missing": 422,
            "provider_not_implemented": 501,
            "provider_not_configured": 503,
            "provider_unavailable": 503,
            "runtime_missing": 503,
            "assets_missing": 503,
            "gpu_unavailable": 503,
            "rate_limited": 429,
            "generation_failed": 502,
            "storage_failed": 500,
        }
        raise HTTPException(
            status_code=status_map.get(exc.error_code, 503),
            detail=payload.model_dump(),
        ) from exc
    logger.info(
        "characters.image.endpoint.done character_id=%s image_id=%s provider=%s",
        character_id, row.id, request.provider_id,
    )
    return character_image_service.to_response(row)


@router.post(
    "/{character_id}/images/{image_id}/accept",
    response_model=CharacterImageActionResponse,
)
async def accept_image(
    character_id: uuid.UUID,
    image_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> CharacterImageActionResponse:
    logger.info("characters.image.accept character_id=%s image_id=%s", character_id, image_id)
    character = await _load_character_or_404(session, character_id)
    image = await character_image_service.get_image(session, character.id, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="image not found")
    # Phase 17F — accepted is a terminal state. Block re-accept on an
    # already accepted image (operator could click again accidentally).
    if image.status == "accepted":
        logger.warning(
            "characters.image.accept.already_accepted character_id=%s image_id=%s",
            character_id, image_id,
        )
        return CharacterImageActionResponse(
            image=character_image_service.to_response(image),
            character_main_reference_image_id=character.main_reference_image_id,
        )
    image = await character_image_service.set_status(session, image, "accepted")
    # Phase 17F + Phase 16 — first accepted image AUTO becomes the
    # character's main reference AND flips ``face_locked=true``. After
    # that, main_reference_image_id is immutable (enforced in
    # set_main_reference handler below).
    if character.main_reference_image_id is None:
        image, character = await character_image_service.set_main_reference(
            session, character, image,
        )
        character.face_locked = True
        await session.commit()
        await session.refresh(character)
        logger.info(
            "characters.image.accept.auto_main_reference character_id=%s image_id=%s face_locked=True",
            character_id, image_id,
        )
    return CharacterImageActionResponse(
        image=character_image_service.to_response(image),
        character_main_reference_image_id=character.main_reference_image_id,
    )


@router.post(
    "/{character_id}/images/{image_id}/reject",
    response_model=CharacterImageActionResponse,
)
async def reject_image(
    character_id: uuid.UUID,
    image_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> CharacterImageActionResponse:
    logger.info("characters.image.reject character_id=%s image_id=%s", character_id, image_id)
    character = await _load_character_or_404(session, character_id)
    image = await character_image_service.get_image(session, character.id, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="image not found")
    # Phase 17F — accepted images are locked. Block reject + archive +
    # delete on them so the operator can't undo a profile picture decision.
    if image.status == "accepted":
        raise HTTPException(
            status_code=409,
            detail="image is accepted (locked) — reject/archive/delete are blocked",
        )
    image = await character_image_service.set_status(session, image, "rejected")
    return CharacterImageActionResponse(
        image=character_image_service.to_response(image),
        character_main_reference_image_id=character.main_reference_image_id,
    )


@router.post(
    "/{character_id}/images/{image_id}/set-main-reference",
    response_model=CharacterImageActionResponse,
)
async def set_main_reference(
    character_id: uuid.UUID,
    image_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> CharacterImageActionResponse:
    logger.info("characters.image.set_main_ref character_id=%s image_id=%s", character_id, image_id)
    character = await _load_character_or_404(session, character_id)
    image = await character_image_service.get_image(session, character.id, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="image not found")
    # Phase 16 — face_locked blocks switching main_reference to a
    # different image. Idempotent re-set on the SAME image still
    # succeeds (so the UI can replay the action without consequences).
    if (
        getattr(character, "face_locked", False)
        and character.main_reference_image_id is not None
        and character.main_reference_image_id != image.id
    ):
        logger.warning(
            "characters.image.set_main_ref.locked character_id=%s tried=%s locked_to=%s",
            character_id, image_id, character.main_reference_image_id,
        )
        raise HTTPException(
            status_code=409,
            detail=(
                f"character face_locked — main_reference_image_id is "
                f"frozen at {character.main_reference_image_id}"
            ),
        )
    image, character = await character_image_service.set_main_reference(
        session, character, image
    )
    # Ensure face_locked is True after any successful set_main_reference.
    if not getattr(character, "face_locked", False):
        character.face_locked = True
        await session.commit()
        await session.refresh(character)
    return CharacterImageActionResponse(
        image=character_image_service.to_response(image),
        character_main_reference_image_id=character.main_reference_image_id,
    )


@router.post(
    "/{character_id}/images/{image_id}/archive",
    response_model=CharacterImageActionResponse,
)
async def archive_image(
    character_id: uuid.UUID,
    image_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> CharacterImageActionResponse:
    logger.info("characters.image.archive character_id=%s image_id=%s", character_id, image_id)
    character = await _load_character_or_404(session, character_id)
    image = await character_image_service.get_image(session, character.id, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="image not found")
    # Phase 17F — accepted images are locked.
    if image.status == "accepted":
        raise HTTPException(
            status_code=409,
            detail="image is accepted (locked) — archive is blocked",
        )
    image = await character_image_service.set_status(session, image, "archived")
    return CharacterImageActionResponse(
        image=character_image_service.to_response(image),
        character_main_reference_image_id=character.main_reference_image_id,
    )


@router.delete(
    "/{character_id}/images/{image_id}",
    status_code=204,
)
async def delete_image(
    character_id: uuid.UUID,
    image_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    logger.info("characters.image.delete.start character_id=%s image_id=%s", character_id, image_id)
    character = await _load_character_or_404(session, character_id)
    image = await character_image_service.get_image(session, character.id, image_id)
    if image is None:
        logger.warning("characters.image.delete.not_found image_id=%s", image_id)
        raise HTTPException(status_code=404, detail="image not found")
    # Phase 17F — accepted images are locked. Block delete on them so
    # the operator can't accidentally remove the character's profile pic.
    if image.status == "accepted":
        logger.warning(
            "characters.image.delete.blocked character_id=%s image_id=%s reason=accepted_locked",
            character_id, image_id,
        )
        raise HTTPException(
            status_code=409,
            detail="image is accepted (locked) — delete is blocked",
        )
    await character_image_service.delete_image(session, character, image)
    logger.info("characters.image.delete.done character_id=%s image_id=%s", character_id, image_id)


@router.get("/{character_id}/images/{image_id}/content")
async def serve_image_content(
    character_id: uuid.UUID,
    image_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> FileResponse:
    character = await _load_character_or_404(session, character_id)
    image = await character_image_service.get_image(session, character.id, image_id)
    if image is None or not image.file_path:
        raise HTTPException(status_code=404, detail="image content not found")
    path = Path(image.file_path)
    if not path.is_file():
        raise HTTPException(status_code=410, detail="image file missing on disk")
    return FileResponse(str(path), media_type="image/png")


# ---------------------------------------------------------------------------
# Phase 15B — Character video library: list every job that produced a
# video for this character, with deep links into the job detail page.
# ---------------------------------------------------------------------------


from pydantic import BaseModel, ConfigDict


class CharacterVideoLinkItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    job_id: uuid.UUID
    job_status: str | None = None
    provider_id: str | None = None
    status: str
    created_at: str
    duration_seconds: float | None = None
    video_artifact_uri: str | None = None
    video_artifact_id: uuid.UUID | None = None


class CharacterVideosResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CharacterVideoLinkItem]
    total: int


@router.get(
    "/{character_id}/videos",
    response_model=CharacterVideosResponse,
)
async def list_character_videos(
    character_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> CharacterVideosResponse:
    """Phase 15B — list every video produced for this character, with a
    job_id deep link so the UI can jump to /jobs/{job_id}."""
    from sqlalchemy import select
    from app.models.character import CharacterVideo
    from app.models.job import Job
    from app.models.artifact import Artifact
    from common.enums import ArtifactType

    logger.info("characters.videos.list.start character_id=%s", character_id)
    await _load_character_or_404(session, character_id)

    rows = (
        await session.execute(
            select(CharacterVideo)
            .where(CharacterVideo.character_id == character_id)
            .order_by(CharacterVideo.created_at.desc())
        )
    ).scalars().all()

    items: list[CharacterVideoLinkItem] = []
    for cv in rows:
        job = (
            await session.execute(select(Job).where(Job.id == cv.job_id))
        ).scalar_one_or_none()
        video_artifact = (
            await session.execute(
                select(Artifact)
                .where(
                    Artifact.job_id == cv.job_id,
                    Artifact.artifact_type == ArtifactType.video.value,
                )
                .order_by(Artifact.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        items.append(
            CharacterVideoLinkItem(
                id=cv.id,
                job_id=cv.job_id,
                job_status=job.status.value if job is not None else None,
                provider_id=cv.provider_id,
                status=cv.status,
                created_at=cv.created_at.isoformat() if cv.created_at else "",
                duration_seconds=(
                    video_artifact.duration_seconds if video_artifact else None
                ),
                video_artifact_uri=video_artifact.uri if video_artifact else None,
                video_artifact_id=video_artifact.id if video_artifact else None,
            )
        )
    logger.info(
        "characters.videos.list.done character_id=%s count=%d",
        character_id, len(items),
    )
    return CharacterVideosResponse(items=items, total=len(items))
