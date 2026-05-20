"""Phase 22 — output orientation on jobs.

Adds ``jobs.orientation`` (varchar 16, default 'landscape') so the
operator can pick mobile-friendly vertical (9:16 portrait) or square
(1:1) output. Default keeps every pre-22 row at 16:9 landscape.

Revision ID: 0008_phase22_orientation
Revises: 0007_phase21_job_type_scene_plan
Create Date: 2026-05-20
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_phase22_orientation"
down_revision: Union[str, None] = "0007_phase21_job_type_scene_plan"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "orientation",
            sa.String(length=16),
            nullable=False,
            server_default="landscape",
        ),
    )


def downgrade() -> None:
    op.drop_column("jobs", "orientation")
