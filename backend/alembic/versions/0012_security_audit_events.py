"""Persistent security audit events table.

Revision ID: 0012_security_audit
Revises: 0011_users_auth
Create Date: 2026-05-20
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012_security_audit"
down_revision: Union[str, None] = "0011_users_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "security_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_username", sa.String(length=150), nullable=True),
        sa.Column("actor_role", sa.String(length=32), nullable=True),
        sa.Column("target_type", sa.String(length=40), nullable=True),
        sa.Column("target_id", sa.String(length=150), nullable=True),
        sa.Column("endpoint", sa.String(length=255), nullable=True),
        sa.Column("method", sa.String(length=10), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=400), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("event_type", "severity", "result", "actor_user_id",
                "target_type", "target_id", "request_id", "created_at"):
        op.create_index(f"ix_security_audit_events_{col}", "security_audit_events", [col])


def downgrade() -> None:
    for col in ("event_type", "severity", "result", "actor_user_id",
                "target_type", "target_id", "request_id", "created_at"):
        op.drop_index(f"ix_security_audit_events_{col}", table_name="security_audit_events")
    op.drop_table("security_audit_events")
