"""Operator overrides on top of the code-driven provider registry — Phase 12.

The code registry in :mod:`app.services.provider_registry` defines the
canonical catalog (label, capabilities, env vars to check). This table
lets the operator override per-provider:

- ``enabled`` — flip a provider off without redeploying.
- ``display_order`` — re-rank the catalog (smaller = earlier).
- ``health_status`` — last result of an explicit health-check probe.
- ``operator_notes`` — free-text reason shown next to a disabled row.

The merge happens at request time via
:func:`app.services.provider_registry.apply_feature_provider_overrides`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class FeatureProvider(Base):
    __tablename__ = "feature_providers"
    __table_args__ = (
        UniqueConstraint("category", "provider_id", name="uq_feature_provider_cat_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    provider_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, server_default="100"
    )
    health_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    operator_notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    last_health_check_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
        server_default=func.now(),
    )
