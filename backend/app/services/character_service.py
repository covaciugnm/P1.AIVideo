"""Character / Persona service — Phase 12.

CRUD + soft-delete + profile snapshotting. Every edit that changes
``profile_json`` appends a row to ``character_versions`` so the
historical state is recoverable. Soft delete sets ``deleted_at`` +
``status='inactive'`` so dropdowns can filter it out; the row stays
so that ``jobs.character_id`` references don't dangle.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.character import (
    Character,
    CharacterImage,
    CharacterVersion,
    CharacterVideo,
)
from app.schemas.character import (
    CharacterCreateRequest,
    CharacterProfile,
    CharacterResponse,
    CharacterSummary,
    CharacterUpdateRequest,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    s = _SLUG_RE.sub("-", text.lower()).strip("-")
    return s or "character"


async def _ensure_unique_slug(session: AsyncSession, base: str) -> str:
    """Find a free slug variant by appending ``-N`` if needed."""
    candidate = base
    suffix = 2
    while True:
        result = await session.execute(
            select(Character.id).where(Character.slug == candidate)
        )
        if result.scalar_one_or_none() is None:
            return candidate
        candidate = f"{base}-{suffix}"
        suffix += 1


async def list_characters(
    session: AsyncSession,
    *,
    include_deleted: bool = False,
    status: str | None = None,
    limit: int = 200,
) -> tuple[list[CharacterSummary], int]:
    stmt = select(Character).order_by(Character.created_at.desc())
    if not include_deleted:
        stmt = stmt.where(Character.deleted_at.is_(None))
    if status is not None:
        stmt = stmt.where(Character.status == status)
    stmt = stmt.limit(limit)
    rows = list((await session.execute(stmt)).scalars().all())

    # Aggregate counts in one round-trip per metric.
    image_counts: dict[uuid.UUID, int] = {}
    video_counts: dict[uuid.UUID, int] = {}
    if rows:
        ids = [r.id for r in rows]
        ic = await session.execute(
            select(CharacterImage.character_id, func.count(CharacterImage.id))
            .where(CharacterImage.character_id.in_(ids))
            .group_by(CharacterImage.character_id)
        )
        image_counts = {cid: int(c) for cid, c in ic.all()}
        vc = await session.execute(
            select(CharacterVideo.character_id, func.count(CharacterVideo.id))
            .where(CharacterVideo.character_id.in_(ids))
            .group_by(CharacterVideo.character_id)
        )
        video_counts = {cid: int(c) for cid, c in vc.all()}

    items = [_to_summary(r, image_counts.get(r.id, 0), video_counts.get(r.id, 0)) for r in rows]
    total_stmt = select(func.count(Character.id))
    if not include_deleted:
        total_stmt = total_stmt.where(Character.deleted_at.is_(None))
    if status is not None:
        total_stmt = total_stmt.where(Character.status == status)
    total = int((await session.execute(total_stmt)).scalar_one())
    return items, total


async def get_character(
    session: AsyncSession, character_id: uuid.UUID, *, include_deleted: bool = False
) -> Character | None:
    result = await session.execute(
        select(Character).where(Character.id == character_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    if row.deleted_at is not None and not include_deleted:
        return None
    return row


async def get_character_by_slug(
    session: AsyncSession, slug: str
) -> Character | None:
    result = await session.execute(
        select(Character).where(Character.slug == slug, Character.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def create_character(
    session: AsyncSession, request: CharacterCreateRequest
) -> Character:
    profile = request.profile
    name = profile.identity.name
    base_slug = _slugify(request.slug or profile.identity.slug or name)
    slug = await _ensure_unique_slug(session, base_slug)
    row = Character(
        name=name,
        slug=slug,
        display_name=profile.identity.display_name,
        status=request.status,
        profile_json=profile.model_dump(mode="json"),
        default_language=request.default_language or profile.voice.preferred_language,
        default_voice_provider_id=(
            request.default_voice_provider_id
            or profile.voice.preferred_tts_provider_id
        ),
        default_image_provider_id=request.default_image_provider_id,
        version_number=1,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    # No snapshot at create time — ``characters.profile_json`` IS v1.
    # ``character_versions`` only carries OLDER versions appended by
    # subsequent edits (see ``update_character``).
    return row


async def update_character(
    session: AsyncSession,
    character: Character,
    request: CharacterUpdateRequest,
) -> Character:
    profile_changed = False
    if request.profile is not None:
        # Snapshot the previous version BEFORE we overwrite the row,
        # so the history is complete even if the new profile is
        # structurally identical.
        session.add(
            CharacterVersion(
                character_id=character.id,
                version_number=character.version_number,
                profile_snapshot_json=character.profile_json,
            )
        )
        new_profile = request.profile.model_dump(mode="json")
        if new_profile != character.profile_json:
            profile_changed = True
        character.profile_json = new_profile
        character.name = request.profile.identity.name
        character.display_name = request.profile.identity.display_name
        character.version_number = character.version_number + 1
    if request.status is not None:
        character.status = request.status
    if request.default_language is not None:
        character.default_language = request.default_language
    if request.default_voice_provider_id is not None:
        character.default_voice_provider_id = request.default_voice_provider_id
    if request.default_image_provider_id is not None:
        character.default_image_provider_id = request.default_image_provider_id
    character.updated_at = _utcnow()
    await session.commit()
    await session.refresh(character)
    return character


async def soft_delete_character(
    session: AsyncSession, character: Character
) -> Character:
    character.deleted_at = _utcnow()
    character.status = "inactive"
    character.updated_at = _utcnow()
    await session.commit()
    await session.refresh(character)
    return character


async def set_main_reference_image(
    session: AsyncSession,
    character: Character,
    image_id: uuid.UUID | None,
) -> Character:
    character.main_reference_image_id = image_id
    character.updated_at = _utcnow()
    await session.commit()
    await session.refresh(character)
    return character


def _to_summary(
    row: Character, image_count: int, video_count: int
) -> CharacterSummary:
    return CharacterSummary(
        id=row.id,
        name=row.name,
        slug=row.slug,
        display_name=row.display_name,
        status=row.status,  # type: ignore[arg-type]
        default_language=row.default_language,
        default_voice_provider_id=row.default_voice_provider_id,
        default_image_provider_id=row.default_image_provider_id,
        main_reference_image_id=row.main_reference_image_id,
        face_locked=bool(getattr(row, "face_locked", False)),
        image_count=image_count,
        video_count=video_count,
        version_number=row.version_number,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def to_response(
    session: AsyncSession, row: Character
) -> CharacterResponse:
    image_count = int(
        (
            await session.execute(
                select(func.count(CharacterImage.id)).where(
                    CharacterImage.character_id == row.id
                )
            )
        ).scalar_one()
    )
    video_count = int(
        (
            await session.execute(
                select(func.count(CharacterVideo.id)).where(
                    CharacterVideo.character_id == row.id
                )
            )
        ).scalar_one()
    )
    return CharacterResponse(
        id=row.id,
        name=row.name,
        slug=row.slug,
        display_name=row.display_name,
        status=row.status,  # type: ignore[arg-type]
        profile=CharacterProfile.model_validate(row.profile_json),
        default_language=row.default_language,
        default_voice_provider_id=row.default_voice_provider_id,
        default_image_provider_id=row.default_image_provider_id,
        main_reference_image_id=row.main_reference_image_id,
        face_locked=bool(getattr(row, "face_locked", False)),
        version_number=row.version_number,
        image_count=image_count,
        video_count=video_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
    )
