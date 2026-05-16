"""Phase 8D recovery metadata.

Adds ``jobs.recovery_metadata`` JSON column for operational state
(cancel timestamps, retry counters, last categorised error). Plain
JSON so we can extend the shape without future migrations for every
field — matches the Phase 4F ``provider_selection`` pattern.

Revision ID: 0002_phase8d_recovery
Revises: 0001_initial
Create Date: 2026-05-15
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002_phase8d_recovery"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("recovery_metadata", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_column("recovery_metadata")
