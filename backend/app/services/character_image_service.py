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
    # Phase 21 iter 2 — also register the generated PNG as an
    # ``ArtifactType.image`` row so it can be consumed by the
    # lipsync pipeline (face_mode=provided_image, image_artifact_id).
    # Stashed on the row as a transient attribute so the API
    # response can include it without a DB-schema change.
    try:
        from app.services import artifact_service
        from common.enums import ArtifactType
        # The generated PNG is rendered as 24-bit RGB without alpha.
        # We don't have a job_id at this point — character images are
        # generated outside any job — so we pass ``job_id=None`` to the
        # artifact service (some pipelines support it; if the service
        # rejects None we fall through silently).
        artifact = await artifact_service.register_artifact(
            session,
            job_id=None,  # type: ignore[arg-type]
            artifact_type=ArtifactType.image.value,
            uri=Path(file_path).as_uri(),
            local_path=str(file_path),
            mime_type="image/png",
            checksum_sha256=checksum,
            size_bytes=len(result.image_bytes),
            metadata_json={
                "phase": "phase21_iter2_character_image_as_artifact",
                "source": "character_image_service.generate_image",
                "character_id": str(character.id),
                "character_image_id": str(image_id),
                "width": result.width,
                "height": result.height,
                "provider_id": request.provider_id,
                "model_id": result.model_id or request.model_id,
                "seed": result.seed,
            },
        )
        await session.commit()
        # Transient attribute for the API response builder.
        row.__dict__["_artifact_id_for_response"] = str(artifact.id)
    except Exception as exc:  # noqa: BLE001 — non-fatal
        logger.warning(
            "characters.image.artifact_registration_failed character_id=%s image_id=%s err=%s",
            character.id, image_id, exc,
        )
    logger.info(
        "characters.generate_image.done character_id=%s image_id=%s provider=%s bytes=%d model=%s",
        character.id, image_id, request.provider_id, len(result.image_bytes), result.model_id or request.model_id,
        extra={"character_id": str(character.id), "provider_id": request.provider_id, "phase": "characters.image.done"},
    )
    return row


# ---------------------------------------------------------------------------
# Phase IG-2 — identity-consistent generation (ComfyUI PuLID-FLUX /
# SDXL-InstantID) on top of the canonical face + full-body references.
# ---------------------------------------------------------------------------


def assert_synthetic_only(character: Character) -> None:
    """Phase IG-5 — block generation only when a character is EXPLICITLY
    flagged as depicting a real person (``identity.is_real_person=true``).

    The product is synthetic-only by construction, so the default (no flag)
    is allowed. NOTE: ``is_public_persona`` means "this synthetic persona
    appears publicly in videos" — it is NOT a real-person flag and must not
    gate generation.
    """
    if os.environ.get("SYNTHETIC_ONLY_ENFORCED", "true").lower() not in (
        "true", "1", "yes",
    ):
        return
    ident = (character.profile_json or {}).get("identity") or {}
    if ident.get("is_real_person") is True:
        raise ProviderUnavailableError(
            "validation_failed",
            "Character is flagged as depicting a REAL person "
            "(identity.is_real_person=true); synthetic-only generation is "
            "enforced. Real-person likeness recreation is not permitted.",
        )


async def _persist_generated_image(
    session: AsyncSession,
    character: Character,
    result,
    *,
    prompt: str,
    negative_prompt: str,
    provider_id: str,
    role: str,
    generation_params: dict,
    reference_face_id: uuid.UUID | None = None,
    reference_full_body_id: uuid.UUID | None = None,
) -> CharacterImage:
    """Shared persist + dual-register for the identity pipeline."""
    image_id = uuid.uuid4()
    target_dir = _character_image_dir(character.id)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ProviderUnavailableError(
            "storage_failed", f"Failed to create artifact directory: {exc}"
        ) from exc
    file_path = target_dir / f"{image_id}.png"
    try:
        file_path.write_bytes(result.image_bytes)
    except OSError as exc:
        raise ProviderUnavailableError(
            "storage_failed", f"Failed to persist PNG: {exc}"
        ) from exc
    checksum = hashlib.sha256(result.image_bytes).hexdigest()
    row = CharacterImage(
        id=image_id,
        character_id=character.id,
        file_path=str(file_path),
        local_url=f"/api/v1/characters/{character.id}/images/{image_id}/content",
        prompt=prompt,
        negative_prompt=negative_prompt,
        provider_id=provider_id,
        model_id=result.model_id,
        seed=result.seed,
        settings_json={"provider_metadata": result.provider_metadata},
        status="draft",
        is_main_reference=False,
        role=role,
        generation_params_json=generation_params,
        reference_face_image_id=reference_face_id,
        reference_full_body_image_id=reference_full_body_id,
        width=result.width,
        height=result.height,
        size_bytes=len(result.image_bytes),
        checksum_sha256=checksum,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    try:
        from app.services import artifact_service
        from common.enums import ArtifactType

        artifact = await artifact_service.register_artifact(
            session,
            job_id=None,  # type: ignore[arg-type]
            artifact_type=ArtifactType.image.value,
            uri=Path(file_path).as_uri(),
            local_path=str(file_path),
            mime_type="image/png",
            checksum_sha256=checksum,
            size_bytes=len(result.image_bytes),
            metadata_json={
                "source": "character_image_service.identity_pipeline",
                "character_id": str(character.id),
                "character_image_id": str(image_id),
                "role": role,
            },
        )
        await session.commit()
        row.__dict__["_artifact_id_for_response"] = str(artifact.id)
    except Exception as exc:  # noqa: BLE001 — non-fatal
        logger.warning("identity image artifact registration failed: %s", exc)
    logger.info(
        "characters.identity_image.done character_id=%s image_id=%s role=%s provider=%s bytes=%d",
        character.id, image_id, role, provider_id, len(result.image_bytes),
    )
    return row


async def generate_initial_character_image(
    session: AsyncSession,
    character: Character,
    *,
    seed: int | None = None,
    width: int = 768,
    height: int = 1024,
    steps: int | None = None,
    guidance_scale: float | None = None,
    workflow_override: str | None = None,
) -> CharacterImage:
    """Phase IG-2 — first image of a NEW character (no reference yet):
    plain text-to-image from the profile to propose candidate faces."""
    from app.services import image_audit
    from app.services.character_prompt_builder import build_initial_prompt
    from app.services.image_workflow_select import select_workflow

    image_audit.record(
        image_audit.CHARACTER_IMAGE_GENERATION_REQUESTED,
        character.id, mode="initial",
    )
    assert_synthetic_only(character)
    sel = select_workflow("initial")
    workflow_name = workflow_override or sel.workflow_name
    image_audit.record(
        image_audit.CHARACTER_IMAGE_GENERATION_APPROVED,
        character.id, mode="initial", workflow=workflow_name, tier=sel.tier,
    )
    pos, neg = build_initial_prompt(character.profile_json)
    provider = get_image_provider("comfyui_local")
    inp = ImageGenerationInput(
        prompt=pos, negative_prompt=neg, model_id=None, seed=seed,
        width=width, height=height, steps=steps, guidance_scale=guidance_scale,
        reference_image_path=None, workflow_name=workflow_name,
    )
    try:
        result = await provider.generate_text_to_image(inp)
    except ProviderUnavailableError as exc:
        image_audit.record(
            image_audit.IMAGE_PROVIDER_FAILURE,
            character.id, mode="initial", error_code=exc.error_code,
        )
        raise
    return await _persist_generated_image(
        session, character, result,
        prompt=pos, negative_prompt=neg, provider_id="comfyui_local",
        role="generated_initial",
        generation_params={
            "mode": "initial", "workflow": workflow_name, "tier": sel.tier,
            "tier_reason": sel.reason, "seed": result.seed,
            "width": width, "height": height,
        },
    )


async def generate_consistent_character_image(
    session: AsyncSession,
    character: Character,
    scene,  # character_prompt_builder.SceneParams
    *,
    seed: int | None = None,
    width: int = 768,
    height: int = 1024,
    steps: int | None = None,
    guidance_scale: float | None = None,
    workflow_override: str | None = None,
) -> CharacterImage:
    """Phase IG-2 — identity-consistent image: same synthetic person in a
    new scene, conditioned on the canonical face + full-body references."""
    from app.services import image_audit, image_face_score
    from app.services.character_prompt_builder import build_consistent_prompt
    from app.services.image_workflow_select import select_workflow

    image_audit.record(
        image_audit.CHARACTER_IMAGE_GENERATION_REQUESTED,
        character.id, mode="consistent",
    )
    assert_synthetic_only(character)
    face_id = character.main_reference_image_id
    body_id = getattr(character, "full_body_reference_image_id", None)
    if not face_id or not body_id:
        raise ProviderUnavailableError(
            "validation_failed",
            "Consistent generation requires BOTH a canonical face and a "
            "canonical full-body reference. Promote two generated images "
            "first (set-main-reference + set-full-body-reference).",
        )
    face_row = await get_image(session, character.id, face_id)
    body_row = await get_image(session, character.id, body_id)
    if face_row is None or not face_row.file_path:
        raise ProviderUnavailableError(
            "reference_image_missing", "Canonical face reference is missing on disk."
        )
    if body_row is None or not body_row.file_path:
        raise ProviderUnavailableError(
            "reference_image_missing", "Canonical full-body reference is missing on disk."
        )
    pos, neg = build_consistent_prompt(character.profile_json, scene)
    sel = select_workflow("consistent")
    workflow_name = workflow_override or sel.workflow_name
    image_audit.record(
        image_audit.CHARACTER_IMAGE_GENERATION_APPROVED,
        character.id, mode="consistent", workflow=workflow_name, tier=sel.tier,
    )
    provider = get_image_provider("comfyui_local")
    inp = ImageGenerationInput(
        prompt=pos, negative_prompt=neg, model_id=None, seed=seed,
        width=width, height=height, steps=steps, guidance_scale=guidance_scale,
        reference_image_path=face_row.file_path,
        face_reference_path=face_row.file_path,
        body_reference_path=body_row.file_path,
        workflow_name=workflow_name,
    )
    try:
        result = await provider.generate_text_to_image(inp)
    except ProviderUnavailableError as exc:
        image_audit.record(
            image_audit.IMAGE_PROVIDER_FAILURE,
            character.id, mode="consistent", error_code=exc.error_code,
        )
        raise
    row = await _persist_generated_image(
        session, character, result,
        prompt=pos, negative_prompt=neg, provider_id="comfyui_local",
        role="generated_variation",
        reference_face_id=face_id, reference_full_body_id=body_id,
        generation_params={
            "mode": "consistent", "workflow": workflow_name, "tier": sel.tier,
            "tier_reason": sel.reason, "seed": result.seed,
            "width": width, "height": height,
            "scene": {
                "scene_prompt": scene.scene_prompt, "outfit_prompt": scene.outfit_prompt,
                "location_prompt": scene.location_prompt, "season": scene.season,
                "mood": scene.mood, "pose": scene.pose, "framing": scene.framing,
            },
        },
    )
    # Optional, isolated identity drift scoring (null when disabled).
    score, drift = image_face_score.score_identity(face_row.file_path, row.file_path)
    if score is not None:
        row.identity_similarity_score = score
        row.identity_drift_warning = bool(drift)
        await session.commit()
        await session.refresh(row)
        if drift:
            image_audit.record(
                image_audit.CHARACTER_IDENTITY_DRIFT_WARNING,
                character.id, image_id=str(row.id), score=round(score, 4),
            )
    return row


async def store_uploaded_reference(
    session: AsyncSession,
    character: Character,
    data: bytes,
    *,
    synthetic_attestation: bool,
) -> CharacterImage:
    """Phase IG-5 — store an operator-uploaded reference candidate.

    Compliance gate: the uploader MUST attest the image is synthetic /
    authorized. Uploads land as ``draft`` with ``moderation_status=pending``
    and CANNOT be promoted to a canonical reference until moderated
    (enforced in the set-*-reference endpoints)."""
    from app.services import image_audit

    if not synthetic_attestation:
        image_audit.record(
            image_audit.CHARACTER_REFERENCE_UPLOAD_BLOCKED,
            character.id, reason="missing_synthetic_attestation",
        )
        raise ProviderUnavailableError(
            "validation_failed",
            "Reference upload requires a synthetic-only attestation. Uploading "
            "a real person's photo is not permitted.",
        )
    assert_synthetic_only(character)
    image_id = uuid.uuid4()
    target_dir = _character_image_dir(character.id)
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = target_dir / f"{image_id}.png"
    file_path.write_bytes(data)
    checksum = hashlib.sha256(data).hexdigest()
    row = CharacterImage(
        id=image_id,
        character_id=character.id,
        file_path=str(file_path),
        local_url=f"/api/v1/characters/{character.id}/images/{image_id}/content",
        prompt=None, negative_prompt=None,
        provider_id="upload", model_id=None, seed=None,
        settings_json={"source": "upload"},
        status="draft",
        is_main_reference=False,
        role="generated_initial",
        generation_params_json={
            "source": "upload",
            "synthetic_attestation": True,
            "moderation_status": "pending",
        },
        size_bytes=len(data),
        checksum_sha256=checksum,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    image_audit.record(
        image_audit.CHARACTER_REFERENCE_UPLOADED,
        character.id, image_id=str(image_id), moderation="pending",
    )
    return row


async def moderate_image(
    session: AsyncSession, image: CharacterImage, *, approve: bool, notes: str = ""
) -> CharacterImage:
    """Phase IG-5 — approve/reject an uploaded reference for canonical use."""
    from app.services import image_audit

    params = dict(image.generation_params_json or {})
    params["moderation_status"] = "approved" if approve else "rejected"
    if notes:
        params["moderation_notes"] = notes
    image.generation_params_json = params
    if not approve:
        image.status = "rejected"
        image.role = "rejected"
    image.updated_at = _utcnow()
    await session.commit()
    await session.refresh(image)
    image_audit.record(
        image_audit.CHARACTER_REFERENCE_MODERATED,
        image.character_id, image_id=str(image.id),
        decision="approved" if approve else "rejected",
    )
    return image


def upload_moderation_blocks_canonical(image: CharacterImage) -> bool:
    """True when ``image`` is an upload that has NOT been moderation-approved
    and therefore cannot become a canonical reference."""
    params = image.generation_params_json or {}
    if params.get("source") != "upload":
        return False
    return params.get("moderation_status") != "approved"


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
    image.role = "canonical_face"  # Phase IG-3
    image.updated_at = _utcnow()
    character = await character_service.set_main_reference_image(
        session, character, image.id
    )
    await session.commit()
    await session.refresh(image)
    return image, character


async def set_full_body_reference(
    session: AsyncSession,
    character: Character,
    image: CharacterImage,
) -> Character:
    """Phase 24 — pin ``image`` as the character's full-body reference.

    Unlike the face main_reference there is no per-image boolean flag;
    the binding lives on ``characters.full_body_reference_image_id``.
    The image is promoted to ``reference`` status so it isn't garbage
    -collected as a draft.
    """
    if image.status not in ("reference", "accepted"):
        image.status = "reference"
    image.role = "canonical_full_body"  # Phase IG-3
    image.updated_at = _utcnow()
    character = await character_service.set_full_body_reference_image(
        session, character, image.id
    )
    await session.commit()
    await session.refresh(image)
    return character


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
    # Phase 21 iter 2 — pick up the transient artifact_id stashed by
    # ``generate_image`` so the frontend can pass it as
    # ``image_artifact_id`` when submitting a talking-head job.
    artifact_id_str = row.__dict__.get("_artifact_id_for_response")
    artifact_id: uuid.UUID | None = None
    if isinstance(artifact_id_str, str):
        try:
            artifact_id = uuid.UUID(artifact_id_str)
        except ValueError:
            artifact_id = None
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
        artifact_id=artifact_id,
        role=getattr(row, "role", None) or "generated_variation",
        identity_similarity_score=getattr(row, "identity_similarity_score", None),
        identity_drift_warning=bool(getattr(row, "identity_drift_warning", False)),
        generation_params_json=getattr(row, "generation_params_json", None),
    )
