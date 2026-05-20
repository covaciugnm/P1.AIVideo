"""Character-image compliance audit events — Phase IG-5.

The DB ``compliance_events`` table is reel-JOB scoped (NOT NULL job_id),
but character image generation happens outside any job. We therefore emit
the compliance/audit trail as structured log records on a dedicated
``image.audit`` logger (auditable + scrapeable), with a stable ``event``
field. If a job-scoped path ever needs DB rows, route through
``compliance`` service instead.
"""
from __future__ import annotations

import logging
import uuid

logger = logging.getLogger("image.audit")

# Stable event vocabulary (mirrors the spec).
CHARACTER_IMAGE_GENERATION_REQUESTED = "CHARACTER_IMAGE_GENERATION_REQUESTED"
CHARACTER_IMAGE_GENERATION_APPROVED = "CHARACTER_IMAGE_GENERATION_APPROVED"
CHARACTER_IMAGE_GENERATION_REJECTED = "CHARACTER_IMAGE_GENERATION_REJECTED"
CHARACTER_REFERENCE_SET = "CHARACTER_REFERENCE_SET"
CHARACTER_REFERENCE_UPLOADED = "CHARACTER_REFERENCE_UPLOADED"
CHARACTER_REFERENCE_UPLOAD_BLOCKED = "CHARACTER_REFERENCE_UPLOAD_BLOCKED"
CHARACTER_REFERENCE_MODERATED = "CHARACTER_REFERENCE_MODERATED"
CHARACTER_IDENTITY_DRIFT_WARNING = "CHARACTER_IDENTITY_DRIFT_WARNING"
IMAGE_PROVIDER_FAILURE = "IMAGE_PROVIDER_FAILURE"


def record(event: str, character_id: uuid.UUID | str, **fields) -> None:
    """Emit one structured audit event."""
    logger.info(
        "image.audit %s character_id=%s %s",
        event, character_id,
        " ".join(f"{k}={v!r}" for k, v in fields.items()),
        extra={"event": event, "character_id": str(character_id), **fields},
    )
