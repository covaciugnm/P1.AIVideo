"""DB-backed API secrets — Phase 12X.

One row per provider credential or local wrapper URL. The
:mod:`app.services.secrets_service` loads every row into
``os.environ`` at startup + on every upsert so the adapter code that
reads ``os.environ.get(...)`` keeps working unchanged across Docker
restarts.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ApiSecret(Base):
    __tablename__ = "api_secrets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_name: Mapped[str] = mapped_column(
        String(160), nullable=False, unique=True, index=True
    )
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    category: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_test_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_test_detail: Mapped[str | None] = mapped_column(String(2000), nullable=True)
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
