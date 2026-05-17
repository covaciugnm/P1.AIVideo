"""Phase 11H — SadTalker DAG real-output contract.

Phase 7E wired the real torch.cuda inference; Phase 11C added the
GPU-wrapper proxy; Phase 11G surfaced Ollama scriptwriter status
correctly. The provider catalog row for SadTalker was still pinned
to ``not_implemented`` even though every gate was satisfied — this
test family pins the corrected behaviour:

1. ``_sadtalker_dynamic_status()`` returns ``available`` when
   ``inspect_status()`` reports ``ready``.
2. The catalog mapping covers every SadTalker status without
   raising and never emits a value outside the ``ProviderInfo``
   status literal set.
3. The orchestrator + backend env contract still names the
   wrapper-proxy variables required for Phase 11C to activate.

These tests run offline — they mock ``SadTalkerProvider.inspect_status``
so they don't depend on a live GPU wrapper. The live verification is
a manual one-time procedure documented in ``docs/runbooks/sadtalker-runtime.md``.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app.services import provider_registry

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "docker" / "compose.dev.yml"


VALID_STATUSES = {"available", "configured", "not_configured", "not_implemented", "disabled", "error"}


# ---------------------------------------------------------------------
# 1. ready → available
# ---------------------------------------------------------------------


def test_sadtalker_ready_maps_to_available():
    with patch(
        "agents.lipsync.providers.sadtalker.provider.SadTalkerProvider.inspect_status",
        return_value={
            "status": "ready",
            "details": {"runtime": {}, "assets": {}},
            "wrapper_url": "http://aivideo-model-sadtalker-1:8080",
        },
    ):
        status, notes, docs = provider_registry._sadtalker_dynamic_status()
    assert status == "available"
    assert "Wrapper:" in notes
    assert "Phase 7D" in notes
    assert "Phase 11C" in notes
    assert docs.endswith("sadtalker-runtime.md")


# ---------------------------------------------------------------------
# 2. Every inspect_status outcome lands inside the ProviderInfo enum.
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw_status",
    ["ready", "not_implemented", "not_configured", "assets_missing", "runtime_missing", "gpu_unavailable"],
)
def test_sadtalker_status_mapping_is_within_provider_enum(raw_status):
    with patch(
        "agents.lipsync.providers.sadtalker.provider.SadTalkerProvider.inspect_status",
        return_value={"status": raw_status, "details": {"assets": {"missing": ["x"]}}},
    ):
        status, _notes, _docs = provider_registry._sadtalker_dynamic_status()
    assert status in VALID_STATUSES, (
        f"raw status {raw_status!r} mapped to {status!r} which is not a ProviderInfo literal"
    )


# ---------------------------------------------------------------------
# 3. The catalog row passes Pydantic validation when ready.
# ---------------------------------------------------------------------


def test_catalog_row_validates_when_ready():
    with patch(
        "agents.lipsync.providers.sadtalker.provider.SadTalkerProvider.inspect_status",
        return_value={
            "status": "ready",
            "details": {"runtime": {}, "assets": {}},
            "wrapper_url": "http://aivideo-model-sadtalker-1:8080",
        },
    ):
        rows = provider_registry._build_video_providers()
    sad = next(r for r in rows if r.provider_id == "sadtalker")
    # Don't isinstance-check ProviderInfo — pydantic instances from
    # different import paths confuse identity. Field access proves the
    # row went through Pydantic validation without raising.
    assert sad.status == "available"
    assert sad.requires_gpu is True
    assert sad.requires_model_files is True
    assert sad.healthcheck_available is True


# ---------------------------------------------------------------------
# 4. inspect_status failure stays defensive (provider import / runtime
#    exception must not break the catalog response).
# ---------------------------------------------------------------------


def test_catalog_handles_inspect_status_failure():
    with patch(
        "agents.lipsync.providers.sadtalker.provider.SadTalkerProvider.inspect_status",
        side_effect=RuntimeError("simulated"),
    ):
        status, notes, docs = provider_registry._sadtalker_dynamic_status()
    assert status == "not_implemented"
    assert "Readiness probe failed" in notes
    assert "RuntimeError" in notes
    assert docs.endswith("sadtalker-runtime.md")


# ---------------------------------------------------------------------
# 5. compose.dev.yml still forwards the Phase 11C wrapper-proxy env on
#    both backend AND orchestrator (regression guard for the original
#    Phase 11C/11G work).
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "SADTALKER_BASE_URL",
        "SADTALKER_ENABLE_REAL_INFERENCE",
        "RUN_REAL_SADTALKER",
        "SADTALKER_MODELS_ROOT",
    ],
)
def test_compose_forwards_sadtalker_env_on_both_services(key):
    """Phase 11C explicitly puts these three (BASE_URL + the two
    real-inference gates) on both backend AND orchestrator environment
    blocks so the wrapper-proxy path activates uniformly. The other
    SadTalker paths (CHECKPOINTS_DIR / GFPGAN_DIR) flow through
    ``env_file: ../.env`` so they don't need a duplicate listing."""
    text = COMPOSE.read_text(encoding="utf-8")
    occurrences = text.count(key)
    assert occurrences >= 2, (
        f"compose.dev.yml must forward {key} on both backend AND orchestrator "
        f"(found {occurrences})"
    )


# ---------------------------------------------------------------------
# 6. Wrapper-side landmark failure code remains stable (Romanian-UI
#    error mapping depends on the exact code string).
# ---------------------------------------------------------------------


def test_wrapper_emits_face_landmark_missing_code():
    wrapper = REPO / "docker" / "model-sadtalker" / "server.py"
    text = wrapper.read_text(encoding="utf-8")
    assert '"face_landmark_missing"' in text
    assert '"video_face_landmark_missing"' in text


def test_orchestrator_handler_branches_on_landmark_code():
    handler = REPO / "agents" / "lipsync" / "handler.py"
    text = handler.read_text(encoding="utf-8")
    assert "video_face_landmark_missing" in text
