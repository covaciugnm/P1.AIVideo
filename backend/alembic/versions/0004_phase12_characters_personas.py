"""Phase 12 — Characters / Personas, image generator registry, video snapshot.

Adds:
- ``characters`` — main persona table with profile_json + soft delete.
- ``character_versions`` — append-only profile snapshots used to keep
  history when a character is edited or deleted.
- ``character_images`` — generated image library per character with
  prompt/seed/provider metadata + accepted/rejected/reference status.
- ``character_videos`` — link table from a video job back to the
  character used at generation time.
- ``feature_providers`` — operator overrides on top of the code-driven
  provider registry (enabled flag, display order, last health-check).
- ``jobs.character_id`` (nullable FK) and ``jobs.character_snapshot``
  (JSON) so old jobs preserve the persona profile used at submit time
  even when the underlying character is later edited or deleted.

Server defaults are chosen so back-fill is trivial. Downgrade drops
everything in reverse order.

Revision ID: 0004_phase12_characters
Revises: 0003_phase11a_language
Create Date: 2026-05-17
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_phase12_characters"
down_revision: Union[str, None] = "0003_phase11a_language"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- feature_providers (operator overrides on the code registry) --------
    op.create_table(
        "feature_providers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("category", sa.String(length=40), nullable=False, index=True),
        sa.Column("provider_id", sa.String(length=80), nullable=False, index=True),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "display_order", sa.Integer(), nullable=False, server_default="100"
        ),
        sa.Column("health_status", sa.String(length=32), nullable=True),
        sa.Column("operator_notes", sa.String(length=1000), nullable=True),
        sa.Column("last_health_check_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "category", "provider_id", name="uq_feature_provider_cat_id"
        ),
    )

    # --- characters ---------------------------------------------------------
    op.create_table(
        "characters",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False, index=True),
        sa.Column("slug", sa.String(length=200), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="active",
        ),
        sa.Column("profile_json", sa.JSON(), nullable=False),
        sa.Column("default_language", sa.String(length=8), nullable=True),
        sa.Column("default_voice_provider_id", sa.String(length=80), nullable=True),
        sa.Column("default_image_provider_id", sa.String(length=80), nullable=True),
        sa.Column("main_reference_image_id", sa.Uuid(), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )

    # --- character_versions (append-only snapshot trail) --------------------
    op.create_table(
        "character_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "character_id",
            sa.Uuid(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("profile_snapshot_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "character_id", "version_number", name="uq_character_version"
        ),
    )

    # --- character_images ---------------------------------------------------
    op.create_table(
        "character_images",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "character_id",
            sa.Uuid(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("file_path", sa.String(length=1000), nullable=True),
        sa.Column("local_url", sa.String(length=1000), nullable=True),
        sa.Column("prompt", sa.String(length=4000), nullable=True),
        sa.Column("negative_prompt", sa.String(length=2000), nullable=True),
        sa.Column("provider_id", sa.String(length=80), nullable=True),
        sa.Column("model_id", sa.String(length=160), nullable=True),
        sa.Column("seed", sa.BigInteger(), nullable=True),
        sa.Column("settings_json", sa.JSON(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "is_main_reference",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # --- character_videos (link from jobs back to characters) ---------------
    op.create_table(
        "character_videos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "character_id",
            sa.Uuid(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("provider_id", sa.String(length=80), nullable=True),
        sa.Column("settings_json", sa.JSON(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # --- jobs.character_id + jobs.character_snapshot ------------------------
    # character_id is nullable so every pre-Phase-12 job stays valid.
    # character_snapshot is a frozen copy of the profile at submit time
    # so edits/deletes never rewrite history.
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("character_id", sa.Uuid(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("character_snapshot", sa.JSON(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_column("character_snapshot")
        batch_op.drop_column("character_id")
    op.drop_table("character_videos")
    op.drop_table("character_images")
    op.drop_table("character_versions")
    op.drop_table("characters")
    op.drop_table("feature_providers")
