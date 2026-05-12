"""Shared enumerations.

These live here (not in `backend/app/models/`) so the agent layer can use
them without importing the backend. `backend/app/models/*.py` re-exports
the relevant enums from this module for backwards compatibility.
"""
from __future__ import annotations

import enum


class JobStatus(str, enum.Enum):
    pending_compliance = "pending_compliance"
    accepted = "accepted"
    published = "published"
    rejected = "rejected"
    failed = "failed"


class ComplianceDecisionType(str, enum.Enum):
    accept = "accept"
    reject = "reject"


class StageStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    rejected = "rejected"
    skipped = "skipped"


class ProviderHealthStatus(str, enum.Enum):
    """Result categories from a model provider's `healthcheck()` call.

    - ``ok``              All declared assets are present; provider is ready
                          to run real inference (if implemented).
    - ``missing_assets``  Provider is implemented but one or more required
                          asset files are missing on disk.
    - ``not_configured``  The provider's models_root env var is unset
                          (e.g. ``SADTALKER_MODELS_ROOT``).
    - ``not_implemented`` Provider is a placeholder (e.g. MuseTalk / Wav2Lip
                          stubs in Phase 3A).
    - ``error``           Some other failure raised by the provider during
                          its healthcheck.
    """

    ok = "ok"
    missing_assets = "missing_assets"
    not_configured = "not_configured"
    not_implemented = "not_implemented"
    error = "error"


class StageName(str, enum.Enum):
    """Canonical stage IDs. Mirrors pipelines/reel_default.yaml."""

    policy_gate = "policy_gate"
    scriptwriter = "scriptwriter"
    voice = "voice"
    face = "face"
    identity_guard = "identity_guard"
    pre_lipsync_auth = "pre_lipsync_auth"
    lipsync = "lipsync"
    editor = "editor"
    qc = "qc"
    export_disclosure_validation = "export_disclosure_validation"
    publisher = "publisher"
