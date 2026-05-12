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


class MissingAssetsError(Exception):
    """A model provider can't run because required asset files are not on disk.

    Always carries the backend name and a list of missing relative paths so
    the operator gets an actionable error.
    """

    def __init__(self, backend: str, missing: list[str]):
        self.backend = backend
        self.missing = list(missing)
        joined = ", ".join(self.missing) if self.missing else "<unspecified>"
        super().__init__(f"{backend}: missing required assets: {joined}")


class UnsupportedBackendError(Exception):
    """A backend name was requested that the registry doesn't know about."""


class ProviderNotImplementedError(NotImplementedError):
    """A provider stub that hasn't reached real-inference state yet.

    Inherits from ``NotImplementedError`` so existing handler code that
    catches ``NotImplementedError`` (e.g. tests using ``pytest.raises``)
    keeps working.
    """
