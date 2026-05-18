"""Character image library — Phase 12.

Persists generated PNGs under ``ARTIFACTS_LOCAL_ROOT/characters/<id>``,
records ``CharacterImage`` rows, and exposes the accept / reject /
set-as-reference workflow used by the operator UI.

The on-disk layout mirrors the existing storage convention (see
``/storage/inputs`` / ``/storage/artifacts``). All paths are passed
through :func:`common.path_safety._validate_local_path` analogues so
the operator can't escape the artifact root via ``..`` tricks.
"""
from __future__ import annotations

import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.character import Character, CharacterImage
from app.schemas.character import (
    CharacterImageGenerateRequest,
    CharacterImageResponse,
)
from app.services import character_service
from app.services.image_providers import (
    ImageGenerationInput,
    ProviderUnavailableError,
    get_image_provider,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _storage_root() -> Path:
    raw = os.environ.get("ARTIFACTS_LOCAL_ROOT", "storage/artifacts").strip()
    return Path(raw)


def _character_image_dir(character_id: uuid.UUID) -> Path:
    return _storage_root() / "characters" / str(character_id)


async def list_images(
    session: AsyncSession, character_id: uuid.UUID
) -> tuple[list[CharacterImage], int]:
    rows = list(
        (
            await session.execute(
                select(CharacterImage)
                .where(CharacterImage.character_id == character_id)
                .order_by(CharacterImage.created_at.desc())
            )
        ).scalars().all()
    )
    total = int(
        (
            await session.execute(
                select(func.count(CharacterImage.id)).where(
                    CharacterImage.character_id == character_id
                )
            )
        ).scalar_one()
    )
    return rows, total


async def get_image(
    session: AsyncSession, character_id: uuid.UUID, image_id: uuid.UUID
) -> CharacterImage | None:
    result = await session.execute(
        select(CharacterImage).where(
            CharacterImage.id == image_id,
            CharacterImage.character_id == character_id,
        )
    )
    return result.scalar_one_or_none()


async def generate_image(
    session: AsyncSession,
    character: Character,
    request: CharacterImageGenerateRequest,
) -> CharacterImage:
    """Run the provider, persist the PNG, record the DB row.

    Raises :class:`ProviderUnavailableError` on provider failure; the
    router translates it to a categorised error response.
    """
    logger.info(
        "characters.generate_image.start character_id=%s provider=%s model=%s",
        character.id, request.provider_id, request.model_id,
        extra={"character_id": str(character.id), "provider_id": request.provider_id, "phase": "characters.image.start"},
    )
    if not request.prompt and not request.reference_image_id and not request.use_main_reference:
        logger.warning(
            "characters.generate_image.rejected character_id=%s reason=missing_inputs",
            character.id,
            extra={"character_id": str(character.id), "phase": "characters.image.reject"},
        )
        raise ProviderUnavailableError(
            "validation_failed",
            "At least one of prompt / reference_image_id / use_main_reference is required.",
        )

    reference_path: str | None = None
    # Phase 17H — once a character has a master reference, ALL generations
    # in that profile auto-use it as img2img input. The operator no longer
    # gets a "don't use reference" escape hatch (the UI removed the
    # checkbox too) — this guarantees face consistency across the profile.
    if character.main_reference_image_id:
        ref_id = character.main_reference_image_id
    elif request.use_main_reference and character.main_reference_image_id:
        # Legacy path retained for safety; equivalent to the branch above.
        ref_id = character.main_reference_image_id
    else:
        ref_id = request.reference_image_id
    if ref_id is not None:
        ref_row = await get_image(session, character.id, ref_id)
        if ref_row is None or not ref_row.file_path:
            raise ProviderUnavailableError(
                "reference_image_missing",
                f"Reference image {ref_id!s} not found for this character.",
            )
        reference_path = ref_row.file_path

    # Phase 15F — auto-translate Romanian prompts to English.
    from app.services.translator import maybe_translate_for_image_gen
    # Phase 16 — auto-build person description from profile + prepend to scene.
    from app.services.character_prompt_builder import (
        build_negative_constraints_en, build_person_description_en,
        merge_scene_with_person,
    )

    en_prompt, prompt_was_translated = maybe_translate_for_image_gen(request.prompt)
    en_negative, negative_was_translated = maybe_translate_for_image_gen(request.negative_prompt)

    # Phase 16 — when a main reference exists OR is being used, AUTO
    # prepend the character's English appearance description so the
    # diffusion model produces the same person across all scenes.
    # The operator's prompt is then treated as scene/context only.
    enriched_prompt = en_prompt
    if reference_path is not None:
        person_desc = build_person_description_en(character.profile_json or {})
        if person_desc:
            enriched_prompt = merge_scene_with_person(person_desc, en_prompt)
            logger.info(
                "characters.image.prompt_enriched character_id=%s scene=%r full=%r",
                character.id, (en_prompt or "")[:80], enriched_prompt[:160],
                extra={"character_id": str(character.id), "phase": "characters.image.enrich"},
            )
        neg_extra = build_negative_constraints_en(character.profile_json or {})
        if neg_extra:
            en_negative = f"{(en_negative or '').strip()}, {neg_extra}".strip(", ")
    en_prompt = enriched_prompt
    if prompt_was_translated:
        logger.info(
            "characters.image.translated_prompt RO→EN orig=%r en=%r",
            (request.prompt or "")[:120], (en_prompt or "")[:120],
            extra={"character_id": str(character.id), "phase": "characters.image.translate"},
        )
    if negative_was_translated:
        logger.info(
            "characters.image.translated_negative RO→EN orig=%r en=%r",
            (request.negative_prompt or "")[:120], (en_negative or "")[:120],
            extra={"character_id": str(character.id), "phase": "characters.image.translate"},
        )

    provider = get_image_provider(request.provider_id)
    provider_input = ImageGenerationInput(
        prompt=en_prompt,
        negative_prompt=en_negative,
        model_id=request.model_id,
        seed=request.seed,
        width=request.width,
        height=request.height,
        steps=request.steps,
        guidance_scale=request.guidance_scale,
        reference_image_path=reference_path,
        extra={
            **({"notes": request.notes} if request.notes else {}),
            **({"original_prompt_ro": request.prompt} if prompt_was_translated else {}),
        },
    )
    mode = "img2img" if reference_path is not None else "txt2img"
    logger.info(
        "characters.generate_image.dispatch character_id=%s provider=%s mode=%s w=%s h=%s steps=%s",
        character.id, request.provider_id, mode, request.width, request.height, request.steps,
        extra={"character_id": str(character.id), "provider_id": request.provider_id, "phase": "characters.image.dispatch"},
    )
    try:
        if reference_path is not None:
            result = await provider.generate_image_to_image(provider_input)
        else:
            result = await provider.generate_text_to_image(provider_input)
    except Exception as exc:
        logger.exception(
            "characters.generate_image.provider_failed character_id=%s provider=%s err=%s",
            character.id, request.provider_id, exc,
            extra={"character_id": str(character.id), "provider_id": request.provider_id, "phase": "characters.image.fail"},
        )
        raise

    # Persist the PNG.
    image_id = uuid.uuid4()
    target_dir = _character_image_dir(character.id)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("character image dir creation failed: %s", exc)
        raise ProviderUnavailableError(
            "storage_failed", f"Failed to create artifact directory: {exc}"
        ) from exc
    file_path = target_dir / f"{image_id}.png"
    try:
        file_path.write_bytes(result.image_bytes)
    except OSError as exc:
        logger.warning("character image write failed: %s", exc)
        raise ProviderUnavailableError(
            "storage_failed", f"Failed to persist PNG: {exc}"
        ) from exc

    checksum = hashlib.sha256(result.image_bytes).hexdigest()
    settings_json = {
        "width": request.width,
        "height": request.height,
        "steps": request.steps,
        "guidance_scale": request.guidance_scale,
        "use_main_reference": request.use_main_reference,
        "reference_image_id": str(request.reference_image_id) if request.reference_image_id else None,
        "provider_metadata": result.provider_metadata,
    }
    row = CharacterImage(
        id=image_id,
        character_id=character.id,
        file_path=str(file_path),
        local_url=f"/api/v1/characters/{character.id}/images/{image_id}/content",
        prompt=request.prompt,
        negative_prompt=request.negative_prompt,
        provider_id=request.provider_id,
        model_id=result.model_id or request.model_id,
        seed=result.seed,
        settings_json=settings_json,
        status="draft",
        is_main_reference=False,
        width=result.width,
        height=result.height,
        size_bytes=len(result.image_bytes),
        checksum_sha256=checksum,
        notes=request.notes,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    logger.info(
        "characters.generate_image.done character_id=%s image_id=%s provider=%s bytes=%d model=%s",
        character.id, image_id, request.provider_id, len(result.image_bytes), result.model_id or request.model_id,
        extra={"character_id": str(character.id), "provider_id": request.provider_id, "phase": "characters.image.done"},
    )
    return row


async def set_status(
    session: AsyncSession,
    image: CharacterImage,
    new_status: str,
) -> CharacterImage:
    image.status = new_status
    image.updated_at = _utcnow()
    await session.commit()
    await session.refresh(image)
    return image


async def set_main_reference(
    session: AsyncSession,
    character: Character,
    image: CharacterImage,
) -> tuple[CharacterImage, Character]:
    # Clear previous main reference.
    if character.main_reference_image_id and character.main_reference_image_id != image.id:
        previous = await get_image(
            session, character.id, character.main_reference_image_id
        )
        if previous is not None:
            previous.is_main_reference = False
            previous.updated_at = _utcnow()
    image.is_main_reference = True
    image.status = "reference"
    image.updated_at = _utcnow()
    character = await character_service.set_main_reference_image(
        session, character, image.id
    )
    await session.commit()
    await session.refresh(image)
    return image, character


async def delete_image(
    session: AsyncSession, character: Character, image: CharacterImage
) -> None:
    if image.is_main_reference:
        await character_service.set_main_reference_image(session, character, None)
    await session.delete(image)
    await session.commit()
    # Best-effort unlink — keep going if the file is already gone.
    try:
        if image.file_path:
            Path(image.file_path).unlink(missing_ok=True)
    except OSError as exc:  # pragma: no cover — defensive
        logger.warning("character image unlink failed: %s", exc)


def to_response(row: CharacterImage) -> CharacterImageResponse:
    return CharacterImageResponse(
        id=row.id,
        character_id=row.character_id,
        file_path=row.file_path,
        local_url=row.local_url,
        prompt=row.prompt,
        negative_prompt=row.negative_prompt,
        provider_id=row.provider_id,
        model_id=row.model_id,
        seed=row.seed,
        settings_json=row.settings_json,
        status=row.status,  # type: ignore[arg-type]
        is_main_reference=row.is_main_reference,
        width=row.width,
        height=row.height,
        size_bytes=row.size_bytes,
        checksum_sha256=row.checksum_sha256,
        notes=row.notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
