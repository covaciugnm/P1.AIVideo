"""Phase 11A — bilingual UI + language-aware jobs + subtitle metadata.

Adds:
- ``operator_settings`` table (singleton row holds operator-wide UI preferences).
- ``jobs.video_language`` (default ``ro``).
- ``jobs.subtitle_enabled`` (default false).
- ``jobs.subtitle_languages`` (JSON list, nullable — empty = follow video_language).
- ``jobs.subtitle_format`` (default ``srt``).
- ``jobs.subtitle_burn_in`` (default false).
- ``jobs.transcript_language`` (nullable).

Server defaults are set so every row inserted before this migration
back-fills cleanly. Downgrade drops the columns + table.

Revision ID: 0003_phase11a_language
Revises: 0002_phase8d_recovery
Create Date: 2026-05-16
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_phase11a_language"
down_revision: Union[str, None] = "0002_phase8d_recovery"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Singleton operator settings table.
    op.create_table(
        "operator_settings",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "ui_language", sa.String(length=8), nullable=False, server_default="ro"
        ),
        sa.Column(
            "default_video_language",
            sa.String(length=8),
            nullable=False,
            server_default="ro",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Seed the singleton row so a fresh deploy doesn't need an
    # initial PATCH before reading.
    op.execute(
        "INSERT INTO operator_settings (id, ui_language, default_video_language) "
        "VALUES (1, 'ro', 'ro')"
    )

    # 2. Language + subtitle columns on jobs.
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "video_language",
                sa.String(length=8),
                nullable=False,
                server_default="ro",
            )
        )
        batch_op.add_column(
            sa.Column(
                "subtitle_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )
        batch_op.add_column(sa.Column("subtitle_languages", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "subtitle_format",
                sa.String(length=8),
                nullable=False,
                server_default="srt",
            )
        )
        batch_op.add_column(
            sa.Column(
                "subtitle_burn_in",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )
        batch_op.add_column(
            sa.Column("transcript_language", sa.String(length=8), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_column("transcript_language")
        batch_op.drop_column("subtitle_burn_in")
        batch_op.drop_column("subtitle_format")
        batch_op.drop_column("subtitle_languages")
        batch_op.drop_column("subtitle_enabled")
        batch_op.drop_column("video_language")
    op.drop_table("operator_settings")
