"""Phase 16 — face_locked flag on characters.

Adds ``characters.face_locked`` boolean to enforce that once an operator
has accepted a master face for a character, the ``main_reference_image_id``
becomes immutable (cannot be unset, cannot be re-pointed at a different
image). Combined with Phase 17F UI/API guards on accepted images, this
gives the operator a guaranteed "same face across all videos" experience.

Default is False so existing characters stay editable. New characters
flip the flag to True automatically the first time an image gets
accepted (see Phase 17F accept_image handler).

Revision ID: 0006_phase16_face_locked
Revises: 0005_phase12x_api_secrets
Create Date: 2026-05-18
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_phase16_face_locked"
down_revision: Union[str, None] = "0005_phase12x_api_secrets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "characters",
        sa.Column(
            "face_locked",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    # Backfill: any character that already has a main_reference_image_id
    # is treated as locked (operator already committed to a face).
    op.execute(
        "UPDATE characters SET face_locked = TRUE "
        "WHERE main_reference_image_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("characters", "face_locked")
