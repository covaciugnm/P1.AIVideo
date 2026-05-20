"""Character / Persona models — Phase 12.

A ``Character`` is a reusable persona that ties together a profile
(used for script prompting + voice + face), a curated image library,
and the videos that have used it. Edits create a new entry in
``character_versions`` so that historical jobs keep the snapshot
they were generated against.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Status literals — kept as strings (not Enum) so adding a new value
# never requires a migration. The frontend validates against the
# /api/v1/characters/lookups payload.
CHARACTER_STATUSES = ("active", "inactive", "draft")
CHARACTER_IMAGE_STATUSES = (
    "draft",
    "accepted",
    "rejected",
    "reference",
    "archived",
)


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    # Full character profile (identity + appearance + education + personality
    # + voice + script behaviour + metadata). The structured shape is
    # described by ``app.schemas.character.CharacterProfile``.
    profile_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    default_language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    default_voice_provider_id: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )
    default_image_provider_id: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )
    main_reference_image_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True
    )
    # Phase 16 — once True, ``main_reference_image_id`` is immutable.
    # Flipped automatically the first time an image is accepted via
    # the accept_image endpoint (see backend/app/api/characters.py).
    face_locked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Phase 24 — a SECOND locked reference: the full-body portrait. The
    # main_reference is the face; this one anchors the full-body look so
    # B-roll / wide shots stay consistent. Locked once the character is
    # activated, same as the face.
    full_body_reference_image_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True
    )
    full_body_locked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    version_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
        server_default=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CharacterVersion(Base):
    """Append-only snapshot trail.

    Every time a character is edited we copy the previous profile into
    a new row here. Old video jobs already carry the snapshot they
    were submitted with on ``jobs.character_snapshot``; this table
    keeps the global history navigable from the operator UI.
    """

    __tablename__ = "character_versions"
    __table_args__ = (
        UniqueConstraint(
            "character_id", "version_number", name="uq_character_version"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    character_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False, server_default=func.now()
    )


class CharacterImage(Base):
    __tablename__ = "character_images"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    character_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    local_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    prompt: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    negative_prompt: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    provider_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    model_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    seed: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    settings_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default="draft"
    )
    is_main_reference: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Phase IG-3 — identity-consistent pipeline metadata.
    #   role: generated_initial | canonical_face | canonical_full_body
    #         | generated_variation | rejected. Derived/maintained alongside
    #         the character's main_reference/full_body bindings (single
    #         source of truth stays the character row; this is the per-image
    #         label for gallery + audit).
    role: Mapped[str] = mapped_column(
        String(32), nullable=False, default="generated_variation",
        server_default="generated_variation", index=True,
    )
    generation_params_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    identity_similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    identity_drift_warning: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    reference_face_image_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    reference_full_body_image_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True
    )
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False, server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
        server_default=func.now(),
    )


class CharacterVideo(Base):
    """Link table from a video job back to the character used at submit time.

    The character profile snapshot lives on the job row itself
    (``jobs.character_snapshot``); this table is the cheap index for
    "which videos has this character appeared in".
    """

    __tablename__ = "character_videos"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    character_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    settings_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False, server_default=func.now()
    )
