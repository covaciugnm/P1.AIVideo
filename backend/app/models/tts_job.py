"""Async TTS job — DB-backed so long (chunked) F5 generations survive a
single HTTP request and the operator can poll progress (chunk N/M).

The job row is the source of truth for status/progress; chunk WAVs are
temp files on disk that get concatenated into the final artifact.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

TTS_JOB_STATUSES = ("queued", "running", "done", "error")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TtsJob(Base):
    __tablename__ = "tts_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="queued", server_default="queued", index=True
    )
    provider_id: Mapped[str] = mapped_column(String(160), nullable=False)
    voice_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="ro", server_default="ro")
    script_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunks_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    chunks_done: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, server_default=func.now(), nullable=False
    )
