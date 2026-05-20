"""Phase IG-3 — character_images identity-pipeline metadata.

Adds role + generation metadata + identity-scoring columns to
``character_images`` for the identity-consistent generation pipeline,
plus indexes for the gallery + audit queries.

Revision ID: 0010_phase_ig3_image_role_metadata
Revises: 0009_phase24_full_body_reference
Create Date: 2026-05-20
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010_ig3_image_meta"
down_revision: Union[str, None] = "0009_phase24_full_body_reference"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "character_images",
        sa.Column(
            "role",
            sa.String(length=32),
            nullable=False,
            server_default="generated_variation",
        ),
    )
    op.add_column(
        "character_images",
        sa.Column("generation_params_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "character_images",
        sa.Column("identity_similarity_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "character_images",
        sa.Column(
            "identity_drift_warning",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "character_images",
        sa.Column("reference_face_image_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "character_images",
        sa.Column("reference_full_body_image_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        "ix_character_images_role", "character_images", ["role"]
    )
    op.create_index(
        "ix_character_images_created_at", "character_images", ["created_at"]
    )
    op.create_index(
        "ix_character_images_provider_id", "character_images", ["provider_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_character_images_provider_id", table_name="character_images")
    op.drop_index("ix_character_images_created_at", table_name="character_images")
    op.drop_index("ix_character_images_role", table_name="character_images")
    op.drop_column("character_images", "reference_full_body_image_id")
    op.drop_column("character_images", "reference_face_image_id")
    op.drop_column("character_images", "identity_drift_warning")
    op.drop_column("character_images", "identity_similarity_score")
    op.drop_column("character_images", "generation_params_json")
    op.drop_column("character_images", "role")
