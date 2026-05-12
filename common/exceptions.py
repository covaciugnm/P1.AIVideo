"""Exceptions shared across the agent layer."""
from __future__ import annotations


class StageError(Exception):
    """Generic stage failure; the runner marks the stage failed and aborts the job."""

    def __init__(self, stage: str, reason: str):
        self.stage = stage
        self.reason = reason
        super().__init__(f"{stage}: {reason}")


class StageRejection(StageError):
    """A compliance/QC gate rejected the job. Distinct from unexpected failure."""


class ComplianceTokenError(Exception):
    """Raised by LipSync (and any other token-gated stage) when the
    `compliance_token` is missing, malformed, expired, or carries the wrong
    claims for the current job."""
