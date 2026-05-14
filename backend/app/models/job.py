"""Job model — Phase 1 + Phase 2.

Stores job metadata only. No binary artifacts. Artifact URIs are recorded
on `StageRun` rows (see stage_run.py).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Enum, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

# Re-export from common so existing `from app.models.job import JobStatus`
# continues to work and there's only one canonical definition.
from common.enums import JobStatus  # noqa: F401

from app.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status"), default=JobStatus.pending_compliance, nullable=False
    )
    brief: Mapped[str] = mapped_column(String(2000), nullable=False)
    target_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    synthetic_person_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    consent_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    watermark_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    c2pa_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Phase 3C: voice routing metadata. `audio_ref` stores the operator-supplied
    # AudioRef as a JSON object — never binary audio.
    voice_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="tts")
    script_text: Mapped[str | None] = mapped_column(String(8000), nullable=True)
    tts_backend: Mapped[str] = mapped_column(String(32), nullable=False, default="piper")
    audio_ref: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Phase 3E: optional face input mode + image reference.
    face_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    image_ref: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # Phase 4F: per-job provider selection (LLM/TTS/video). Plain JSON dict
    # with a whitelisted shape (see app.schemas.providers.ProviderSelection).
    # Nullable so every pre-4F test keeps passing.
    provider_selection: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )
