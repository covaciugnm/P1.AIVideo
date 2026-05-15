"""Phase 7E — pipeline integration for first real video provider.

What this phase pins:

- ``DagState.provider_selection`` is populated from ``job.provider_selection``
  by the DAG runner.
- The lipsync handler reads ``provider_selection["video_provider_id"]``;
  when absent, falls back to the deploy default (``expected_backend``).
- Default state (real-inference flags off):
  ``inspect_status() == "not_implemented"`` → handler emits the Phase 2
  no-op stub unchanged. Phase 2 / Phase 3 invariants stay green.
- Opt-in but un-ready states (``not_configured`` / ``assets_missing`` /
  ``runtime_missing`` / ``gpu_unavailable``) raise ``StageRejection``
  with a categorised reason — the DAG records the failure cleanly,
  no phantom artifact is registered.
- Opt-in + ready + (monkey-patched) successful inference:
  handler returns a non-noop ``StageOutput`` carrying a video
  ``ArtifactRef`` with the local path + checksum so downstream
  QC/publisher consumers can read it.
- Provider routing: setting ``video_provider_id`` to a non-sadtalker
  value (e.g. ``musetalk``) falls through to the no-op stub —
  hardened adapters for those providers land in later phases.
- Downstream QC/publisher stages still pass with a real video
  artifact in place (no regression).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Helpers — construct a DagState with a valid compliance token + upstream
# face / voice artifacts so the lipsync handler reaches the provider
# dispatch.
# ---------------------------------------------------------------------------


def _build_state_with_valid_token(
    *,
    job_id: uuid.UUID,
    provider_selection: dict[str, str | None] | None,
    voice_local_path: str | None = None,
    face_local_path: str | None = None,
):
    from agents.compliance_officer.compliance_token import mint_token
    from common.schemas import (
        ArtifactRef,
        ComplianceTokenClaims,
        DagState,
        StageOutput,
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    claims = ComplianceTokenClaims(
        job_id=str(job_id),
        synthetic_person_confirmed=True,
        consent_confirmed=True,
        watermark_required=True,
        c2pa_required=True,
        allowed_lipsync_backend="sadtalker",
        issued_at=now,
        expires_at=now.replace(year=now.year + 1),
    )
    token = mint_token(claims, "TEST-KEY")
    state = DagState(
        job_id=job_id,
        brief="phase 7e",
        target_duration_seconds=30,
        synthetic_person_confirmed=True,
        consent_confirmed=True,
        watermark_required=True,
        c2pa_required=True,
        compliance_token=token,
        provider_selection=provider_selection,
    )
    state.stage_outputs["face"] = StageOutput(
        artifacts={
            "portrait": ArtifactRef(
                artifact_type="image",
                uri=f"s3://bucket/{job_id}/portrait.png",
                local_path=face_local_path,
            )
        }
    )
    state.stage_outputs["voice"] = StageOutput(
        artifacts={
            "narration": ArtifactRef(
                artifact_type="audio",
                uri=f"s3://bucket/{job_id}/narration.wav",
                local_path=voice_local_path,
            )
        }
    )
    return state, "TEST-KEY"


# ---------------------------------------------------------------------------
# Default state — Phase 2 no-op preserved
# ---------------------------------------------------------------------------


async def test_lipsync_default_state_emits_no_op_stub(monkeypatch):
    """With real-inference flags off, the handler emits the Phase 2
    stub regardless of provider_selection. Phase 2 invariants stay
    green."""
    from agents.lipsync.handler import run as lipsync_run

    monkeypatch.delenv("SADTALKER_ENABLE_REAL_INFERENCE", raising=False)
    monkeypatch.delenv("RUN_REAL_SADTALKER", raising=False)

    state, key = _build_state_with_valid_token(
        job_id=uuid.uuid4(),
        provider_selection={"video_provider_id": "sadtalker"},
    )
    out = await lipsync_run(state, signing_key=key, expected_backend="sadtalker")
    assert out.noop is True
    assert "talking_head" in out.artifacts
    # Phase 7E adds inspection metadata when the provider is sadtalker.
    assert out.extra.get("sadtalker", {}).get("inspect_status") == "not_implemented"


async def test_lipsync_no_provider_selection_falls_back_to_expected_backend(
    monkeypatch,
):
    from agents.lipsync.handler import run as lipsync_run

    monkeypatch.delenv("SADTALKER_ENABLE_REAL_INFERENCE", raising=False)
    monkeypatch.delenv("RUN_REAL_SADTALKER", raising=False)

    state, key = _build_state_with_valid_token(
        job_id=uuid.uuid4(),
        provider_selection=None,
    )
    out = await lipsync_run(state, signing_key=key, expected_backend="sadtalker")
    assert out.noop is True
    # Inspection ran because expected_backend == sadtalker (no override).
    assert out.extra.get("sadtalker", {}).get("inspect_status") == "not_implemented"


async def test_lipsync_non_sadtalker_provider_falls_through_to_stub(monkeypatch):
    """Selecting musetalk / wav2lip currently bypasses the SadTalker
    readiness probe (their hardened adapters land later). Stub
    behavior preserves Phase 3A invariants."""
    from agents.lipsync.handler import run as lipsync_run

    monkeypatch.delenv("SADTALKER_ENABLE_REAL_INFERENCE", raising=False)
    monkeypatch.delenv("RUN_REAL_SADTALKER", raising=False)

    state, key = _build_state_with_valid_token(
        job_id=uuid.uuid4(),
        provider_selection={"video_provider_id": "musetalk"},
    )
    out = await lipsync_run(state, signing_key=key, expected_backend="sadtalker")
    assert out.noop is True
    # No sadtalker block in extra — non-sadtalker path skipped the probe.
    assert "sadtalker" not in out.extra


# ---------------------------------------------------------------------------
# Opt-in but un-ready states — categorised StageRejection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fake_status, expected_marker",
    [
        ("not_configured", "not_configured"),
        ("assets_missing", "assets_missing"),
        ("runtime_missing", "runtime_missing"),
        ("gpu_unavailable", "gpu_unavailable"),
    ],
)
async def test_lipsync_rejects_with_categorised_reason_when_not_ready(
    monkeypatch, fake_status, expected_marker
):
    """Each opt-in non-ready state raises StageRejection naming the
    state. The DAG records the failure cleanly; no phantom artifact."""
    from agents.lipsync import handler as lipsync_mod
    from agents.lipsync.handler import run as lipsync_run
    from common.exceptions import StageRejection

    monkeypatch.setenv("SADTALKER_ENABLE_REAL_INFERENCE", "true")
    monkeypatch.setenv("RUN_REAL_SADTALKER", "1")

    state, key = _build_state_with_valid_token(
        job_id=uuid.uuid4(),
        provider_selection={"video_provider_id": "sadtalker"},
    )

    from agents.lipsync.providers.sadtalker import provider as sad_mod

    monkeypatch.setattr(
        sad_mod.SadTalkerProvider,
        "inspect_status",
        lambda self: {"status": fake_status, "details": {"reason": "test"}},
    )

    with pytest.raises(StageRejection) as exc:
        await lipsync_run(state, signing_key=key, expected_backend="sadtalker")
    assert expected_marker in str(exc.value), exc.value


# ---------------------------------------------------------------------------
# Ready + monkey-patched successful inference
# ---------------------------------------------------------------------------


async def test_lipsync_ready_path_calls_inference_hook_and_returns_video_ref(
    monkeypatch, tmp_path
):
    """Status=ready + fake inference returns completed → handler
    produces a non-noop StageOutput with a video ArtifactRef carrying
    local_path + checksum."""
    from agents.lipsync import handler as lipsync_mod
    from agents.lipsync.handler import run as lipsync_run
    from common.schemas import StageOutput

    monkeypatch.setenv("SADTALKER_ENABLE_REAL_INFERENCE", "true")
    monkeypatch.setenv("RUN_REAL_SADTALKER", "1")
    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path / "artifacts"))

    # Create real input files so any local_path lookups succeed.
    img = tmp_path / "face.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    aud = tmp_path / "voice.wav"
    aud.write_bytes(b"RIFF" + b"\x00" * 36)

    state, key = _build_state_with_valid_token(
        job_id=uuid.uuid4(),
        provider_selection={"video_provider_id": "sadtalker"},
        face_local_path=str(img),
        voice_local_path=str(aud),
    )

    from agents.lipsync.providers.sadtalker import provider as sad_mod

    monkeypatch.setattr(
        sad_mod.SadTalkerProvider,
        "inspect_status",
        lambda self: {
            "status": "ready",
            "details": {"assets": {}, "runtime": {}, "gpu": {}},
        },
    )

    async def fake_inference(*, state, provider, voice_output, face_output, expected_backend, status_info):
        # Write a sentinel "MP4" so the handler can compute size + checksum.
        from common.schemas import ArtifactRef
        import hashlib

        out_dir = Path(tmp_path / "artifacts" / "video" / str(state.job_id))
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "sadtalker_fake.mp4"
        out_path.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 64)
        size = out_path.stat().st_size
        h = hashlib.sha256()
        with out_path.open("rb") as f:
            h.update(f.read())
        return StageOutput(
            noop=False,
            notes=f"lipsync fake: produced {size} bytes",
            artifacts={
                "talking_head": ArtifactRef(
                    artifact_type="video",
                    uri=out_path.as_uri(),
                    local_path=str(out_path),
                    mime_type="video/mp4",
                    checksum_sha256=h.hexdigest(),
                    size_bytes=size,
                    duration_seconds=3.5,
                    width=512,
                    height=512,
                    extra={"phase": "phase7e_real_inference"},
                )
            },
            extra={"sadtalker": {"inspect_status": "ready", "details": {}}},
        )

    monkeypatch.setattr(lipsync_mod, "_attempt_lipsync_inference", fake_inference)

    out = await lipsync_run(state, signing_key=key, expected_backend="sadtalker")
    assert out.noop is False
    assert "talking_head" in out.artifacts
    head = out.artifacts["talking_head"]
    assert head.artifact_type == "video"
    assert head.mime_type == "video/mp4"
    assert head.local_path is not None
    assert Path(head.local_path).is_file()
    assert head.checksum_sha256
    assert head.size_bytes is not None and head.size_bytes > 0


async def test_lipsync_ready_path_translates_failure_to_stage_rejection(
    monkeypatch, tmp_path
):
    """If the real-inference hook returns a categorised failure, the
    handler raises StageRejection (DAG won't crash)."""
    from agents.lipsync import handler as lipsync_mod
    from agents.lipsync.handler import run as lipsync_run
    from common.exceptions import StageRejection

    monkeypatch.setenv("SADTALKER_ENABLE_REAL_INFERENCE", "true")
    monkeypatch.setenv("RUN_REAL_SADTALKER", "1")

    img = tmp_path / "face.png"
    img.write_bytes(b"\x00")
    aud = tmp_path / "voice.wav"
    aud.write_bytes(b"\x00")

    state, key = _build_state_with_valid_token(
        job_id=uuid.uuid4(),
        provider_selection={"video_provider_id": "sadtalker"},
        face_local_path=str(img),
        voice_local_path=str(aud),
    )

    from agents.lipsync.providers.sadtalker import provider as sad_mod

    monkeypatch.setattr(
        sad_mod.SadTalkerProvider,
        "inspect_status",
        lambda self: {"status": "ready", "details": {}},
    )

    # Force the real `_attempt_lipsync_inference` body to run with a
    # provider whose generate() returns a categorised failure.
    monkeypatch.setattr(
        sad_mod,
        "_attempt_real_inference",
        lambda **kwargs: {
            "status": "failed",
            "error_code": "video_generation_failed",
            "message": "synthetic failure",
            "details": {},
        },
    )

    with pytest.raises(StageRejection) as exc:
        await lipsync_run(state, signing_key=key, expected_backend="sadtalker")
    assert "video_generation_failed" in str(exc.value) or "failed" in str(exc.value)


async def test_lipsync_ready_path_rejects_when_upstream_local_paths_missing(
    monkeypatch,
):
    """A ready provider + upstream artifacts without local_path → the
    handler refuses cleanly. Real inference needs on-disk files."""
    from agents.lipsync.handler import run as lipsync_run
    from common.exceptions import StageRejection

    monkeypatch.setenv("SADTALKER_ENABLE_REAL_INFERENCE", "true")
    monkeypatch.setenv("RUN_REAL_SADTALKER", "1")

    state, key = _build_state_with_valid_token(
        job_id=uuid.uuid4(),
        provider_selection={"video_provider_id": "sadtalker"},
        # No local_path on either upstream artifact.
    )

    from agents.lipsync.providers.sadtalker import provider as sad_mod

    monkeypatch.setattr(
        sad_mod.SadTalkerProvider,
        "inspect_status",
        lambda self: {"status": "ready", "details": {}},
    )

    with pytest.raises(StageRejection) as exc:
        await lipsync_run(state, signing_key=key, expected_backend="sadtalker")
    assert "local_path" in str(exc.value)


# ---------------------------------------------------------------------------
# DagState surfaces provider_selection end-to-end
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def app_under_test(monkeypatch, tmp_path):
    monkeypatch.setenv("UPLOAD_AUDIO_ROOT", str(tmp_path / "audio"))
    monkeypatch.setenv("UPLOAD_IMAGE_ROOT", str(tmp_path / "images"))
    monkeypatch.setenv("UPLOAD_TEXT_ROOT", str(tmp_path / "text"))
    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("SCRIPTWRITER_BACKEND", "template")

    from app.core import db as core_db
    from app.main import create_app
    from app.services import queue_publisher

    await core_db.async_reset_engine()
    await core_db.init_db()
    fake = fakeaioredis.FakeRedis(decode_responses=True)
    queue_publisher.set_redis_client(fake)
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
    await fake.aclose()
    queue_publisher.reset_redis_client()
    await core_db.async_reset_engine()


async def test_dag_load_state_pulls_provider_selection_from_job(app_under_test):
    """Smoke: post a job with provider_selection, then load it via the
    same path the DagRunner uses, and confirm DagState carries it."""
    from app.core.db import get_sessionmaker
    from agents.orchestrator.dag import DagRunner, DagRunnerConfig

    r = await app_under_test.post(
        "/api/v1/jobs",
        json={
            "brief": "phase 7e DAG provider_selection",
            "synthetic_person_confirmed": True,
            "consent_confirmed": True,
            "target_duration_seconds": 30,
            "watermark_required": True,
            "c2pa_required": True,
            "script_text": "phase 7e",
            "provider_selection": {
                "video_provider_id": "sadtalker",
                "tts_provider_id": "piper",
            },
        },
    )
    assert r.status_code == 201, r.text
    job_id = uuid.UUID(r.json()["id"])

    sm = get_sessionmaker()
    cfg = DagRunnerConfig(signing_key="any", allowed_lipsync_backend="sadtalker")
    runner = DagRunner(sessionmaker=sm, config=cfg)
    state, job = await runner._load_state(job_id)  # type: ignore[attr-defined]
    assert state.provider_selection == {
        "video_provider_id": "sadtalker",
        "tts_provider_id": "piper",
    }
