"""Phase 11A — singleton operator settings row.

There's no multi-user auth in the dashboard today, so we keep a single
row keyed by ``id=1`` that holds operator-wide preferences (UI language,
default video language, etc.). When auth lands later this becomes the
default for new users; existing data stays valid because the schema is
otherwise unchanged.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.languages import DEFAULT_UI_LANGUAGE, DEFAULT_VIDEO_LANGUAGE
from app.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


SINGLETON_ID: int = 1


class OperatorSettings(Base):
    __tablename__ = "operator_settings"

    # server_default mirrors the alembic migration so autogenerate drift
    # detection doesn't flag a phantom alter_column on every test run.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=SINGLETON_ID)
    ui_language: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default=DEFAULT_UI_LANGUAGE,
        server_default=DEFAULT_UI_LANGUAGE,
    )
    default_video_language: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default=DEFAULT_VIDEO_LANGUAGE,
        server_default=DEFAULT_VIDEO_LANGUAGE,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
        server_default=func.now(),
    )
