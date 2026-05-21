"""Async TTS jobs table.

Revision ID: 0013_tts_jobs
Revises: 0012_security_audit
Create Date: 2026-05-21
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013_tts_jobs"
down_revision: Union[str, None] = "0012_security_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tts_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("provider_id", sa.String(length=160), nullable=False),
        sa.Column("voice_id", sa.String(length=160), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=False, server_default="ro"),
        sa.Column("script_text", sa.Text(), nullable=False),
        sa.Column("chunks_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunks_done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("artifact_id", sa.Uuid(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tts_jobs_status", "tts_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_tts_jobs_status", table_name="tts_jobs")
    op.drop_table("tts_jobs")
