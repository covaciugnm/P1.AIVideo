"""Phase 24 — full-body reference image + lock on characters.

Adds ``characters.full_body_reference_image_id`` (uuid, nullable) and
``characters.full_body_locked`` (bool, default false). Mirrors the
Phase 16 face_locked / main_reference_image_id pair: once a character is
activated, both the face AND the full-body reference are frozen.

Revision ID: 0009_phase24_full_body_reference
Revises: 0008_phase22_orientation
Create Date: 2026-05-20
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_phase24_full_body_reference"
down_revision: Union[str, None] = "0008_phase22_orientation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "characters",
        sa.Column("full_body_reference_image_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "characters",
        sa.Column(
            "full_body_locked",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("characters", "full_body_locked")
    op.drop_column("characters", "full_body_reference_image_id")
