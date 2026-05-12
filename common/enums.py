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
