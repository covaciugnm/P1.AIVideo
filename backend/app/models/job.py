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
    # Phase 8D: operational recovery metadata — cancellation timestamps,
    # retry counters, last categorised error, etc. Plain JSON so the
    # shape can evolve without schema migrations for every new field.
    # Nullable so every pre-8D test keeps passing.
    recovery_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Phase 11A — language + subtitle metadata.
    # ``video_language`` ISO-ish code (e.g. ``ro`` / ``en``); validated
    # against ``app.core.languages.LANGUAGES``.
    video_language: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default="ro", default="ro"
    )
    subtitle_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    # JSON list of language codes; defaults to ``[]`` (which the API
    # auto-expands to ``[video_language]`` when subtitle_enabled=True).
    subtitle_languages: Mapped[list | None] = mapped_column(JSON, nullable=True)
    subtitle_format: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default="srt", default="srt"
    )
    subtitle_burn_in: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    # Optional override for transcript / forced-alignment language.
    # Defaults to ``video_language`` when unset.
    transcript_language: Mapped[str | None] = mapped_column(
        String(8), nullable=True, default=None
    )
    # Phase 12 — Character / Persona binding.
    # ``character_id`` is a soft FK (not enforced at DB level) so a
    # deleted character doesn't cascade-delete history; the
    # ``character_snapshot`` JSON column holds a frozen copy of the
    # profile the job was submitted with so edits/deletes never
    # rewrite already-generated content.
    character_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    character_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )
