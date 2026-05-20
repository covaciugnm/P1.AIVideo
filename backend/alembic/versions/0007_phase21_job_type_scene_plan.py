"""Phase 21 — job_type + scene_plan on jobs.

Adds:
  - ``jobs.job_type`` (varchar 32, default 'talking_head') — discriminator
    between the three pipeline variants (talking_head | scenes_only |
    news_presenter). Default keeps every pre-21 row behaving like the
    original single-portrait + lipsync flow.
  - ``jobs.scene_plan`` (JSON, nullable) — per-scene script + visual
    descriptions for the scenes_only + news_presenter pipelines. NULL
    for talking_head jobs.

No data backfill needed beyond the server-side default; old rows read
as ``job_type='talking_head'`` / ``scene_plan=NULL`` automatically.

Revision ID: 0007_phase21_job_type_scene_plan
Revises: 0006_phase16_face_locked
Create Date: 2026-05-19
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_phase21_job_type_scene_plan"
down_revision: Union[str, None] = "0006_phase16_face_locked"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "job_type",
            sa.String(length=32),
            nullable=False,
            server_default="talking_head",
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "scene_plan",
            sa.JSON(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("jobs", "scene_plan")
    op.drop_column("jobs", "job_type")
