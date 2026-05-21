"""Async TTS jobs — run the (chunked) F5 generation in the background so a
long script never blocks/times-out a single HTTP request.

Status + final artifact are persisted in ``tts_jobs`` (durable). Live per-chunk
progress is kept in a small in-memory map (avoids a sync DB write from the
per-chunk callback); the poll endpoint overlays it onto the DB row.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tts_job import TtsJob

logger = logging.getLogger(__name__)

# job_id(str) -> (chunks_done, chunks_total) while running.
_LIVE: dict[str, tuple[int, int]] = {}


def live_progress(job_id) -> tuple[int, int] | None:
    return _LIVE.get(str(job_id))


async def create_job(
    session: AsyncSession, *, provider_id: str, voice_id: str | None,
    language: str, script_text: str,
) -> TtsJob:
    from app.api.tts import _chunk_script_for_tts  # lazy: avoid circular import
    import os
    max_chars = int(os.environ.get("F5TTS_RO_CHUNK_MAX_CHARS", "180"))
    total = len(_chunk_script_for_tts(script_text, max_chars=max_chars))
    job = TtsJob(
        id=uuid.uuid4(), status="queued", provider_id=provider_id, voice_id=voice_id,
        language=language or "ro", script_text=script_text, chunks_total=total, chunks_done=0,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def run_tts_job(job_id: uuid.UUID) -> None:
    """Background entrypoint — own session; never raises into the caller."""
    from fastapi import HTTPException

    from app.api.tts import TTSGenerateRequest, _generate_via_f5tts_ro
    from app.core import db as core_db

    sm = core_db.get_sessionmaker()
    async with sm() as session:
        job = await session.get(TtsJob, job_id)
        if job is None:
            return
        job.status = "running"
        await session.commit()
        _LIVE[str(job_id)] = (0, job.chunks_total)

        def _cb(done: int, total: int) -> None:
            _LIVE[str(job_id)] = (done, total)

        payload = TTSGenerateRequest(
            script_text=job.script_text,
            tts_provider_id=job.provider_id,
            language=job.language,
        )
        try:
            resp = await _generate_via_f5tts_ro(payload, session, job.provider_id, progress_cb=_cb)
            job.status = "done"
            job.artifact_id = uuid.UUID(str(resp.artifact_id)) if resp.artifact_id else None
            job.chunks_done = job.chunks_total
        except HTTPException as exc:
            d = exc.detail if isinstance(exc.detail, dict) else {}
            job.status = "error"
            job.error_code = str(d.get("code", "tts_generation_failed"))[:64]
            job.error_message = str(d.get("message", exc.detail))[:1000]
        except Exception as exc:  # noqa: BLE001
            logger.exception("tts job %s failed", job_id)
            job.status = "error"
            job.error_code = "tts_generation_failed"
            job.error_message = f"{type(exc).__name__}: {exc}"[:1000]
        await session.commit()
        _LIVE.pop(str(job_id), None)


def to_public(job: TtsJob) -> dict:
    live = live_progress(job.id)
    done = live[0] if live else job.chunks_done
    total = live[1] if live else job.chunks_total
    return {
        "id": str(job.id),
        "status": job.status,
        "chunks_done": done,
        "chunks_total": total,
        "artifact_id": str(job.artifact_id) if job.artifact_id else None,
        "provider_id": job.provider_id,
        "voice_id": job.voice_id,
        "error_code": job.error_code,
        "error_message": job.error_message,
    }
