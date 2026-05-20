"""Character / Persona service — Phase 12.

CRUD + soft-delete + profile snapshotting. Every edit that changes
``profile_json`` appends a row to ``character_versions`` so the
historical state is recoverable. Soft delete sets ``deleted_at`` +
``status='inactive'`` so dropdowns can filter it out; the row stays
so that ``jobs.character_id`` references don't dangle.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

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


# Phase 23 — character lifecycle states.
#   editing : draft / under edit. Everything (face, DOB, voice) editable.
#             Reserves its TTS voice so no other character can grab it.
#   active  : committed. Face / date_of_birth / gender / voice are IMMUTABLE.
#             Can generate photos + videos. Still reserves its voice.
#   retired : decommissioned. CANNOT generate photos/videos. RELEASES its
#             TTS voice so another character may claim it.
# Legacy "inactive" (old soft-delete status) is treated as retired.
STATUS_EDITING = "editing"
STATUS_ACTIVE = "active"
STATUS_RETIRED = "retired"
_VOICE_HOLDING_STATUSES = (STATUS_EDITING, STATUS_ACTIVE)
# Statuses that block photo / video generation.
_GEN_BLOCKED_STATUSES = (STATUS_RETIRED, "inactive")


class CharacterRuleError(ValueError):
    """Raised when a lifecycle / immutability / exclusivity rule is
    violated. The API layer maps it to HTTP 409."""


async def assigned_voice_ids(
    session: AsyncSession, *, exclude_character_id: uuid.UUID | None = None
) -> set[str]:
    """Phase 23 — set of TTS voice ids currently RESERVED by characters.

    A voice is reserved while its character is in ``editing`` or
    ``active`` (not retired, not soft-deleted). Retiring a character
    frees its voice. ``exclude_character_id`` lets the owning character
    keep seeing its own voice as available when re-saving.
    """
    stmt = select(Character.default_voice_provider_id).where(
        Character.deleted_at.is_(None),
        Character.status.in_(_VOICE_HOLDING_STATUSES),
        Character.default_voice_provider_id.is_not(None),
    )
    if exclude_character_id is not None:
        stmt = stmt.where(Character.id != exclude_character_id)
    rows = await session.execute(stmt)
    return {v for (v,) in rows.all() if v}


async def assert_voice_available(
    session: AsyncSession,
    voice_id: str | None,
    *,
    exclude_character_id: uuid.UUID | None = None,
) -> None:
    """Phase 23 — raise CharacterRuleError if ``voice_id`` is already
    reserved by another non-retired character."""
    if not voice_id:
        return
    taken = await assigned_voice_ids(session, exclude_character_id=exclude_character_id)
    if voice_id in taken:
        raise CharacterRuleError(
            f"TTS voice {voice_id!r} is already assigned to another active "
            "or editing character. Retire that character to free the voice, "
            "or pick a different voice."
        )


def is_generation_blocked(character: Character) -> bool:
    """Phase 23 — True when the character is retired/inactive and so
    cannot produce new photos or videos."""
    return (character.status or "") in _GEN_BLOCKED_STATUSES


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


async def _name_taken(
    session: AsyncSession, name: str, *, exclude_id: uuid.UUID | None = None
) -> bool:
    """Case-insensitive name uniqueness among non-deleted characters."""
    stmt = select(Character.id).where(
        func.lower(Character.name) == name.strip().lower(),
        Character.deleted_at.is_(None),
    )
    if exclude_id is not None:
        stmt = stmt.where(Character.id != exclude_id)
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def _unique_name(session: AsyncSession, base: str) -> str:
    """Return a free name variant, appending ' (N)' if ``base`` is taken."""
    if not await _name_taken(session, base):
        return base
    n = 2
    while await _name_taken(session, f"{base} ({n})"):
        n += 1
    return f"{base} ({n})"


async def list_characters(
    session: AsyncSession,
    *,
    include_deleted: bool = False,
    status: str | None = None,
    limit: int = 200,
) -> tuple[list[CharacterSummary], int]:
    # Always alphabetical by name (Phase 23 — operator request).
    stmt = select(Character).order_by(func.lower(Character.name).asc())
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
    # Names are unique among non-deleted characters (once used, can't reuse).
    if await _name_taken(session, name):
        raise CharacterRuleError(f"A character named {name!r} already exists.")
    base_slug = _slugify(request.slug or profile.identity.slug or name)
    slug = await _ensure_unique_slug(session, base_slug)
    # Phase 23 — enforce TTS voice exclusivity at create time.
    requested_voice = (
        request.default_voice_provider_id
        or profile.voice.preferred_tts_provider_id
    )
    await assert_voice_available(session, requested_voice)
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


def _identity_immutable_fields(profile_json: dict) -> dict:
    """Phase 23/24 — fields that become immutable once a character is
    active. The face + full-body images are guarded separately via
    face_locked / full_body_locked; this covers the biographical
    identity the operator asked to freeze: date of birth, gender,
    place/nationality of origin, and the formal education record.
    """
    p = profile_json or {}
    ident = p.get("identity") or {}
    edu = p.get("education") or {}
    return {
        "identity.date_of_birth": ident.get("date_of_birth"),
        "identity.gender": ident.get("gender"),
        "identity.place_of_birth": ident.get("place_of_birth"),
        "identity.nationality": ident.get("nationality"),
        "identity.native_language": ident.get("native_language"),
        "education.education_level": edu.get("education_level"),
        "education.field_of_study": edu.get("field_of_study"),
    }


async def update_character(
    session: AsyncSession,
    character: Character,
    request: CharacterUpdateRequest,
) -> Character:
    # Phase 23 — immutability gate. Once a character is ACTIVE, the
    # face (face_locked), date_of_birth, gender, and TTS voice are
    # frozen. To change them the operator must first move the
    # character back to ``editing`` (status transition endpoint).
    locked = (character.status or "") == STATUS_ACTIVE

    if request.profile is not None and locked:
        old_imm = _identity_immutable_fields(character.profile_json)
        new_imm = _identity_immutable_fields(request.profile.model_dump(mode="json"))
        for field, old_val in old_imm.items():
            if new_imm.get(field) != old_val:
                raise CharacterRuleError(
                    f"{field} is immutable while the character is "
                    f"active (was {old_val!r}, got {new_imm.get(field)!r}). "
                    "Move the character to 'editing' first."
                )

    # Phase 23 — voice change rules: blocked while active; otherwise
    # must not collide with another character's reserved voice.
    if request.default_voice_provider_id is not None:
        if locked and request.default_voice_provider_id != character.default_voice_provider_id:
            raise CharacterRuleError(
                "The TTS voice is immutable while the character is active. "
                "Move it to 'editing' to change the voice."
            )
        await assert_voice_available(
            session,
            request.default_voice_provider_id,
            exclude_character_id=character.id,
        )

    # Name uniqueness on rename (case-insensitive, excluding self).
    if request.profile is not None:
        new_name = request.profile.identity.name
        if new_name.strip().lower() != (character.name or "").strip().lower():
            if await _name_taken(session, new_name, exclude_id=character.id):
                raise CharacterRuleError(f"A character named {new_name!r} already exists.")

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


async def transition_status(
    session: AsyncSession,
    character: Character,
    new_status: str,
) -> Character:
    """Phase 23 — explicit lifecycle transition.

    Valid moves:
      editing → active   (commit; requires a voice + a locked face)
      active  → editing  (re-open for changes)
      active  → retired  (decommission; frees the voice)
      editing → retired  (abandon a draft; frees the voice)
      retired → editing  (revive — voice must still be free)
    """
    cur = (character.status or "").lower()
    nxt = new_status.lower()
    valid = {
        (STATUS_EDITING, STATUS_ACTIVE),
        (STATUS_ACTIVE, STATUS_EDITING),
        (STATUS_ACTIVE, STATUS_RETIRED),
        (STATUS_EDITING, STATUS_RETIRED),
        (STATUS_RETIRED, STATUS_EDITING),
        ("inactive", STATUS_EDITING),  # legacy revive
    }
    if cur == nxt:
        return character
    if (cur, nxt) not in valid:
        raise CharacterRuleError(
            f"invalid status transition {cur!r} → {nxt!r}. Allowed: "
            "editing→active, active→editing, active→retired, "
            "editing→retired, retired→editing."
        )
    if nxt == STATUS_ACTIVE:
        # Activation requires a committed face + a voice.
        if not character.main_reference_image_id:
            raise CharacterRuleError(
                "cannot activate: the character has no main reference image "
                "(accept a generated face first)."
            )
        if not character.default_voice_provider_id:
            raise CharacterRuleError(
                "cannot activate: no TTS voice assigned. Pick a voice while "
                "the character is in 'editing'."
            )
        # Re-check the voice is still free (another character might have
        # been activated meanwhile).
        await assert_voice_available(
            session, character.default_voice_provider_id,
            exclude_character_id=character.id,
        )
    if nxt == STATUS_EDITING and cur == STATUS_RETIRED:
        # Reviving a retired character — its voice may have been claimed
        # by someone else while it was retired.
        await assert_voice_available(
            session, character.default_voice_provider_id,
            exclude_character_id=character.id,
        )
    character.status = nxt
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


async def count_related(session: AsyncSession, character: Character) -> dict[str, int]:
    """How many images / videos / jobs a hard purge would remove."""
    from app.models.job import Job
    cid = character.id
    imgs = (await session.execute(
        select(func.count()).select_from(CharacterImage).where(CharacterImage.character_id == cid)
    )).scalar_one()
    vids = (await session.execute(
        select(func.count()).select_from(CharacterVideo).where(CharacterVideo.character_id == cid)
    )).scalar_one()
    jobs = (await session.execute(
        select(func.count()).select_from(Job).where(Job.character_id == cid)
    )).scalar_one()
    return {"images": int(imgs), "videos": int(vids), "jobs": int(jobs)}


async def purge_character(session: AsyncSession, character: Character) -> dict[str, int]:
    """HARD delete: removes the character and EVERYTHING tied to it —
    identity row, image rows + files on disk, versions, video rows, and the
    associated job rows. Irreversible. Returns counts of what was removed."""
    import shutil
    from sqlalchemy import delete as sa_delete

    from app.models.job import Job
    from app.services.character_image_service import _character_image_dir

    cid = character.id
    counts = await count_related(session, character)

    # 1) image files on disk (whole per-character dir)
    try:
        img_dir = _character_image_dir(cid)
        if img_dir.exists():
            shutil.rmtree(img_dir, ignore_errors=True)
    except Exception as exc:  # noqa: BLE001 — file cleanup must not block the purge
        logger.warning("purge: image dir cleanup failed for %s: %s", cid, exc)

    # 2) DB rows (children first, then the character)
    await session.execute(sa_delete(CharacterImage).where(CharacterImage.character_id == cid))
    await session.execute(sa_delete(CharacterVideo).where(CharacterVideo.character_id == cid))
    await session.execute(sa_delete(CharacterVersion).where(CharacterVersion.character_id == cid))
    await session.execute(sa_delete(Job).where(Job.character_id == cid))
    await session.delete(character)
    await session.commit()
    logger.info("characters.purge.done id=%s removed=%s", cid, counts)
    return counts


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


async def set_full_body_reference_image(
    session: AsyncSession,
    character: Character,
    image_id: uuid.UUID | None,
) -> Character:
    """Phase 24 — pin the full-body reference image (companion to the
    face main_reference)."""
    character.full_body_reference_image_id = image_id
    character.updated_at = _utcnow()
    await session.commit()
    await session.refresh(character)
    return character


async def clone_character(
    session: AsyncSession, source: Character, *, new_name: str | None = None
) -> Character:
    """Phase 24 — duplicate a character's PROFILE into a brand-new row
    that opens in ``editing``.

    The clone deliberately drops the exclusive bindings so the operator
    can re-pick them on the copy: TTS voice, face/full-body references,
    and the locks. This is the supported way to "branch" an active
    character when you want to change a frozen field.
    """
    profile = dict(source.profile_json or {})
    ident = dict(profile.get("identity") or {})
    # Clone the IDENTITY only; the name must be unique (can't reuse a name).
    base_name = await _unique_name(session, new_name or f"{source.name} (copy)")
    ident["name"] = base_name
    # Drop the inherited display_name/slug so they regenerate cleanly.
    ident.pop("display_name", None)
    ident.pop("slug", None)
    profile["identity"] = ident

    slug = await _ensure_unique_slug(session, _slugify(base_name))
    row = Character(
        name=base_name,
        slug=slug,
        display_name=None,
        status=STATUS_EDITING,
        profile_json=profile,
        default_language=source.default_language,
        # Exclusive bindings are NOT copied — the clone picks its own.
        default_voice_provider_id=None,
        default_image_provider_id=source.default_image_provider_id,
        main_reference_image_id=None,
        face_locked=False,
        full_body_reference_image_id=None,
        full_body_locked=False,
        version_number=1,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


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
        full_body_reference_image_id=getattr(row, "full_body_reference_image_id", None),
        full_body_locked=bool(getattr(row, "full_body_locked", False)),
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
        full_body_reference_image_id=getattr(row, "full_body_reference_image_id", None),
        full_body_locked=bool(getattr(row, "full_body_locked", False)),
        version_number=row.version_number,
        image_count=image_count,
        video_count=video_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
    )
