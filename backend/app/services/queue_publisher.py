"""Redis Streams publisher.

Phase 1 invariant: messages carry references only — IDs, status, small flags.
No binary payloads ever. See docs/architecture/data-flow.md.
"""
from __future__ import annotations

import json
from typing import Any

import redis.asyncio as redis

from app.core.config import settings
from app.models.job import Job

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.get_redis_url(), decode_responses=True)
    return _client


def set_redis_client(client: redis.Redis) -> None:
    """Test helper: inject a fakeredis (or any redis-compatible) client."""
    global _client
    _client = client


def reset_redis_client() -> None:
    global _client
    _client = None


async def publish_job_created(job: Job) -> None:
    """Fan out a `job.created` event to the compliance + orchestrator streams.

    The orchestrator stream is the one the orchestrator consumes; the
    compliance stream feeds the audit-event consumer (observation channel).
    """
    payload: dict[str, Any] = {
        "event": "job.created",
        "job_id": str(job.id),
        "status": job.status.value,
        "target_duration_seconds": job.target_duration_seconds,
        "watermark_required": job.watermark_required,
        "c2pa_required": job.c2pa_required,
    }
    client = get_redis()
    data = {"data": json.dumps(payload)}
    await client.xadd(settings.queue_topic_orchestrator, data)
    await client.xadd(settings.queue_topic_compliance, data)
