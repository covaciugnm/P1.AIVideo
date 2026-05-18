"""Phase 12X — DB-backed API secrets.

Adds ``api_secrets`` table so the operator can persist provider
credentials (HF_TOKEN, FLUX_BFL_API_KEY, STABILITY_API_KEY, …) +
local wrapper URLs through the right-sidebar Keys page. The backend
loads every row into ``os.environ`` at startup so adapter code that
reads ``os.environ.get(...)`` keeps working unchanged — and survives
Docker restarts.

Revision ID: 0005_phase12x_api_secrets
Revises: 0004_phase12_characters
Create Date: 2026-05-17
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_phase12x_api_secrets"
down_revision: Union[str, None] = "0004_phase12_characters"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_secrets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key_name", sa.String(length=160), nullable=False, unique=True, index=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("category", sa.String(length=40), nullable=True, index=True),
        sa.Column("last_tested_at", sa.DateTime(), nullable=True),
        sa.Column("last_test_status", sa.String(length=20), nullable=True),
        sa.Column("last_test_detail", sa.String(length=2000), nullable=True),
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


def downgrade() -> None:
    op.drop_table("api_secrets")
