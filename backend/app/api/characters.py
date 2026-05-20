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

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

logger = logging.getLogger(__name__)
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.schemas.character import (
    CharacterCloneRequest,
    CharacterCreateRequest,
    CharacterGenerateConsistentRequest,
    CharacterGenerateInitialRequest,
    CharacterImageActionResponse,
    CharacterImageGenerateError,
    CharacterImageGenerateRequest,
    CharacterImageListResponse,
    CharacterImageResponse,
    CharacterListResponse,
    CharacterLookupsResponse,
    CharacterResponse,
    CharacterScriptContextResponse,
    CharacterStatusRequest,
    CharacterSummary,
    CharacterUpdateRequest,
)
from app.services import (
    character_image_service,
    character_lookups,
    character_script_context,
    character_service,
    image_audit,
    provider_registry,
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


@router.get("/available-voices", response_model=list[str])
async def list_available_voices(
    character_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> list[str]:
    """Phase 23 — TTS voice provider_ids NOT reserved by other active/
    editing characters. The owning character (``character_id``) keeps
    seeing its own voice as available."""
    taken = await character_service.assigned_voice_ids(
        session, exclude_character_id=character_id
    )
    catalog = provider_registry.list_providers_by_category("tts")
    return [
        p.provider_id
        for p in catalog
        if p.status in ("configured", "available") and p.provider_id not in taken
    ]


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
    try:
        row = await character_service.create_character(session, request)
    except character_service.CharacterRuleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
    try:
        character = await character_service.update_character(session, character, request)
    except character_service.CharacterRuleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    logger.info("characters.update.done id=%s", character.id)
    return await character_service.to_response(session, character)


@router.post("/{character_id}/status", response_model=CharacterResponse)
async def transition_character_status(
    character_id: uuid.UUID,
    request: CharacterStatusRequest,
    session: AsyncSession = Depends(get_db_session),
) -> CharacterResponse:
    """Phase 23 — explicit lifecycle transition (editing/active/retired).

    Retiring frees the character's TTS voice for reuse; activating
    locks face/DOB/gender/voice. See character_service.transition_status.
    """
    character = await _load_character_or_404(session, character_id)
    try:
        character = await character_service.transition_status(
            session, character, request.status
        )
    except character_service.CharacterRuleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    logger.info("characters.status.done id=%s → %s", character.id, character.status)
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
    if character_service.is_generation_blocked(character):
        raise HTTPException(
            status_code=409,
            detail=f"character status '{character.status}' does not allow image generation",
        )
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


# ---------------------------------------------------------------------------
# Phase IG-2 — identity-consistent generation endpoints.
# ---------------------------------------------------------------------------

_IMAGE_ERROR_STATUS = {
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

_ASPECT_DIMS = {
    "portrait": (768, 1024),
    "landscape": (1024, 768),
    "square": (1024, 1024),
}
_QUALITY_STEPS = {"draft": 12, "standard": 24, "high": 36}


def _raise_image_error(exc: ProviderUnavailableError):
    from app.schemas.character import CharacterImageGenerateError

    payload = CharacterImageGenerateError(
        error_code=exc.error_code,  # type: ignore[arg-type]
        detail=exc.detail,
        provider_id="comfyui_local",
        fallback=exc.fallback,
    )
    raise HTTPException(
        status_code=_IMAGE_ERROR_STATUS.get(exc.error_code, 503),
        detail=payload.model_dump(),
    ) from exc


@router.post(
    "/{character_id}/images/generate-initial",
    response_model=CharacterImageResponse,
)
async def generate_initial_image(
    character_id: uuid.UUID,
    request: CharacterGenerateInitialRequest,
    session: AsyncSession = Depends(get_db_session),
) -> CharacterImageResponse:
    """Phase IG-2 — first image of a new character (text-to-image)."""
    character = await _load_character_or_404(session, character_id)
    if character_service.is_generation_blocked(character):
        raise HTTPException(
            status_code=409,
            detail=f"character status '{character.status}' does not allow image generation",
        )
    w, h = _ASPECT_DIMS[request.aspect_ratio]
    try:
        row = await character_image_service.generate_initial_character_image(
            session, character, seed=request.seed, width=w, height=h,
            steps=_QUALITY_STEPS[request.quality_preset],
            workflow_override=request.workflow_override,
        )
    except ProviderUnavailableError as exc:
        _raise_image_error(exc)
    return character_image_service.to_response(row)


@router.post(
    "/{character_id}/images/generate-consistent",
    response_model=CharacterImageResponse,
)
async def generate_consistent_image(
    character_id: uuid.UUID,
    request: CharacterGenerateConsistentRequest,
    session: AsyncSession = Depends(get_db_session),
) -> CharacterImageResponse:
    """Phase IG-2 — identity-consistent image conditioned on the canonical
    face + full-body references."""
    from app.services.character_prompt_builder import SceneParams

    character = await _load_character_or_404(session, character_id)
    if character_service.is_generation_blocked(character):
        raise HTTPException(
            status_code=409,
            detail=f"character status '{character.status}' does not allow image generation",
        )
    w, h = _ASPECT_DIMS[request.aspect_ratio]
    scene = SceneParams(
        scene_prompt=request.scene_prompt,
        outfit_prompt=request.outfit_prompt,
        location_prompt=request.location_prompt,
        season=request.season,
        mood=request.mood,
        pose=request.pose,
        framing=request.framing,
        negative_prompt_extra=request.negative_prompt_extra,
    )
    try:
        row = await character_image_service.generate_consistent_character_image(
            session, character, scene, seed=request.seed, width=w, height=h,
            steps=_QUALITY_STEPS[request.quality_preset],
            workflow_override=request.provider_override,
        )
    except ProviderUnavailableError as exc:
        _raise_image_error(exc)
    return character_image_service.to_response(row)


@router.post(
    "/{character_id}/images/upload-reference",
    response_model=CharacterImageResponse,
)
async def upload_reference_image(
    character_id: uuid.UUID,
    file: UploadFile = File(...),
    synthetic_attestation: bool = Form(False),
    session: AsyncSession = Depends(get_db_session),
) -> CharacterImageResponse:
    """Phase IG-5 — upload a reference candidate. Gated: requires a
    synthetic-only attestation; lands as a moderation-pending draft that
    cannot become canonical until approved via the moderate endpoint."""
    character = await _load_character_or_404(session, character_id)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="empty upload")
    try:
        row = await character_image_service.store_uploaded_reference(
            session, character, data, synthetic_attestation=synthetic_attestation,
        )
    except ProviderUnavailableError as exc:
        _raise_image_error(exc)
    return character_image_service.to_response(row)


@router.post(
    "/{character_id}/images/{image_id}/moderate",
    response_model=CharacterImageResponse,
)
async def moderate_reference_image(
    character_id: uuid.UUID,
    image_id: uuid.UUID,
    decision: str = Form(...),
    notes: str = Form(""),
    session: AsyncSession = Depends(get_db_session),
) -> CharacterImageResponse:
    """Phase IG-5 — approve/reject an uploaded reference for canonical use."""
    character = await _load_character_or_404(session, character_id)
    image = await character_image_service.get_image(session, character.id, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="image not found")
    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=422, detail="decision must be approve|reject")
    image = await character_image_service.moderate_image(
        session, image, approve=(decision == "approve"), notes=notes,
    )
    return character_image_service.to_response(image)


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
    # Phase IG-5 — an uploaded reference cannot become canonical until it
    # has been moderation-approved.
    if character_image_service.upload_moderation_blocks_canonical(image):
        raise HTTPException(
            status_code=409,
            detail="uploaded reference is pending moderation — approve it first",
        )
    image, character = await character_image_service.set_main_reference(
        session, character, image
    )
    image_audit.record(
        image_audit.CHARACTER_REFERENCE_SET, character_id,
        image_id=str(image_id), kind="face",
    )
    # Ensure face_locked is True after any successful set_main_reference.
    if not getattr(character, "face_locked", False):
        character.face_locked = True
        await session.commit()
        await session.refresh(character)
    return CharacterImageActionResponse(
        image=character_image_service.to_response(image),
        character_main_reference_image_id=character.main_reference_image_id,
        character_full_body_reference_image_id=character.full_body_reference_image_id,
    )


@router.post(
    "/{character_id}/images/{image_id}/set-full-body-reference",
    response_model=CharacterImageActionResponse,
)
async def set_full_body_reference(
    character_id: uuid.UUID,
    image_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> CharacterImageActionResponse:
    """Phase 24 — pin the full-body reference image (companion to the
    face main_reference). Frozen once ``full_body_locked`` is set;
    idempotent re-set on the same image still succeeds."""
    logger.info(
        "characters.image.set_full_body character_id=%s image_id=%s",
        character_id, image_id,
    )
    character = await _load_character_or_404(session, character_id)
    image = await character_image_service.get_image(session, character.id, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="image not found")
    if (
        getattr(character, "full_body_locked", False)
        and character.full_body_reference_image_id is not None
        and character.full_body_reference_image_id != image.id
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "character full_body_locked — full_body_reference_image_id is "
                f"frozen at {character.full_body_reference_image_id}"
            ),
        )
    if character_image_service.upload_moderation_blocks_canonical(image):
        raise HTTPException(
            status_code=409,
            detail="uploaded reference is pending moderation — approve it first",
        )
    character = await character_image_service.set_full_body_reference(
        session, character, image
    )
    image_audit.record(
        image_audit.CHARACTER_REFERENCE_SET, character_id,
        image_id=str(image_id), kind="full_body",
    )
    if not getattr(character, "full_body_locked", False):
        character.full_body_locked = True
        await session.commit()
        await session.refresh(character)
    return CharacterImageActionResponse(
        image=character_image_service.to_response(image),
        character_main_reference_image_id=character.main_reference_image_id,
        character_full_body_reference_image_id=character.full_body_reference_image_id,
    )


@router.post("/{character_id}/clone", response_model=CharacterResponse, status_code=201)
async def clone_character(
    character_id: uuid.UUID,
    request: CharacterCloneRequest | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> CharacterResponse:
    """Phase 24 — duplicate a character's profile into a new row that
    opens in ``editing``. The clone drops the exclusive bindings (TTS
    voice, face + full-body references, locks) so the operator can
    change the previously-frozen fields on the copy."""
    source = await _load_character_or_404(session, character_id)
    new_name = request.new_name if request else None
    try:
        clone = await character_service.clone_character(
            session, source, new_name=new_name
        )
    except character_service.CharacterRuleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    logger.info("characters.clone.done source=%s clone=%s", source.id, clone.id)
    return await character_service.to_response(session, clone)


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
