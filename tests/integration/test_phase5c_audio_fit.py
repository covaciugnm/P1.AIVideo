"""Phase 5C — /api/v1/audio/fit-check.

Validates the duration-delta classification against a stub audio
artifact (size + checksum aren't relevant — only ``duration_seconds``
matters here).
"""
from __future__ import annotations

import uuid

import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def app_under_test(monkeypatch, tmp_path):
    monkeypatch.setenv("PROVIDED_AUDIO_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("SCRIPTWRITER_BACKEND", "template")

    from app.core import db as core_db
    from app.main import create_app
    from app.services import queue_publisher

    await core_db.async_reset_engine()
    await core_db.init_db()

    fake = fakeaioredis.FakeRedis(decode_responses=True)
    queue_publisher.set_redis_client(fake)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    await fake.aclose()
    queue_publisher.reset_redis_client()
    await core_db.async_reset_engine()


async def _register_audio_artifact(*, duration_seconds: float, job_id: uuid.UUID | None = None) -> uuid.UUID:
    """Insert an audio Artifact row with the given duration."""
    from app.core.db import get_sessionmaker
    from app.services import artifact_service

    sm = get_sessionmaker()
    async with sm() as session:
        art = await artifact_service.register_artifact(
            session,
            artifact_type="audio",
            uri="file:///tmp/fake.wav",
            local_path="/tmp/fake.wav",
            mime_type="audio/wav",
            checksum_sha256="deadbeef" * 8,
            size_bytes=1024,
            duration_seconds=duration_seconds,
            sample_rate=22050,
            channels=1,
            job_id=job_id,
        )
        await session.commit()
        return art.id


def _valid_job_payload() -> dict:
    return {
        "brief": "Three bedtime habits.",
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "target_duration_seconds": 30,
        "watermark_required": True,
        "c2pa_required": True,
        "script_text": "Hello.",
    }


# ---------------------------------------------------------------------------
# Classification matrix
# ---------------------------------------------------------------------------


async def test_fit_check_exact_fit_is_ok(app_under_test):
    aid = await _register_audio_artifact(duration_seconds=30.0)
    r = await app_under_test.post(
        "/api/v1/audio/fit-check",
        json={"audio_artifact_id": str(aid), "target_duration_seconds": 30},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fit_status"] == "ok"
    assert body["recommendation"] == "accept"
    assert body["delta_seconds"] == 0.0


async def test_fit_check_within_one_second_is_ok(app_under_test):
    aid = await _register_audio_artifact(duration_seconds=29.4)
    r = await app_under_test.post(
        "/api/v1/audio/fit-check",
        json={"audio_artifact_id": str(aid), "target_duration_seconds": 30},
    )
    body = r.json()
    assert body["fit_status"] == "ok"
    assert body["recommendation"] == "accept"


async def test_fit_check_too_short_in_soft_window_recommends_longer_script(app_under_test):
    aid = await _register_audio_artifact(duration_seconds=28.0)
    r = await app_under_test.post(
        "/api/v1/audio/fit-check",
        json={"audio_artifact_id": str(aid), "target_duration_seconds": 30},
    )
    body = r.json()
    assert body["fit_status"] == "too_short"
    assert body["recommendation"] == "regenerate_script_longer"
    assert body["delta_seconds"] == -2.0


async def test_fit_check_too_short_beyond_soft_window_recommends_target_adjust(app_under_test):
    aid = await _register_audio_artifact(duration_seconds=20.0)
    r = await app_under_test.post(
        "/api/v1/audio/fit-check",
        json={"audio_artifact_id": str(aid), "target_duration_seconds": 30},
    )
    body = r.json()
    assert body["fit_status"] == "too_short"
    assert body["recommendation"] == "adjust_target_duration"


async def test_fit_check_too_long_in_soft_window_recommends_shorter_script(app_under_test):
    aid = await _register_audio_artifact(duration_seconds=32.5)
    r = await app_under_test.post(
        "/api/v1/audio/fit-check",
        json={"audio_artifact_id": str(aid), "target_duration_seconds": 30},
    )
    body = r.json()
    assert body["fit_status"] == "too_long"
    assert body["recommendation"] == "regenerate_script_shorter"


async def test_fit_check_too_long_beyond_soft_window_recommends_target_adjust(app_under_test):
    aid = await _register_audio_artifact(duration_seconds=45.0)
    r = await app_under_test.post(
        "/api/v1/audio/fit-check",
        json={"audio_artifact_id": str(aid), "target_duration_seconds": 30},
    )
    body = r.json()
    assert body["fit_status"] == "too_long"
    assert body["recommendation"] == "adjust_target_duration"


async def test_fit_check_missing_audio_when_artifact_omitted_and_no_job_audio(app_under_test):
    # Job with no audio artifacts attached.
    r = await app_under_test.post("/api/v1/jobs", json=_valid_job_payload())
    job_id = r.json()["id"]
    r2 = await app_under_test.post(
        "/api/v1/audio/fit-check",
        json={"job_id": job_id},
    )
    body = r2.json()
    assert body["fit_status"] == "missing_audio"
    assert body["recommendation"] == "upload_better_audio"
    assert body["audio_duration_seconds"] is None
    assert body["delta_seconds"] is None
    assert body["target_duration_seconds"] == 30


# ---------------------------------------------------------------------------
# Job inheritance for target_duration_seconds
# ---------------------------------------------------------------------------


async def test_fit_check_inherits_target_from_job(app_under_test):
    r = await app_under_test.post(
        "/api/v1/jobs", json={**_valid_job_payload(), "target_duration_seconds": 45}
    )
    job_id = uuid.UUID(r.json()["id"])
    aid = await _register_audio_artifact(duration_seconds=44.5, job_id=job_id)
    r2 = await app_under_test.post(
        "/api/v1/audio/fit-check",
        json={"job_id": str(job_id), "audio_artifact_id": str(aid)},
    )
    body = r2.json()
    assert body["target_duration_seconds"] == 45
    assert body["fit_status"] == "ok"


async def test_fit_check_auto_picks_most_recent_audio_for_job(app_under_test):
    r = await app_under_test.post("/api/v1/jobs", json=_valid_job_payload())
    job_id = uuid.UUID(r.json()["id"])
    await _register_audio_artifact(duration_seconds=10.0, job_id=job_id)
    latest = await _register_audio_artifact(duration_seconds=30.0, job_id=job_id)

    r2 = await app_under_test.post(
        "/api/v1/audio/fit-check", json={"job_id": str(job_id)}
    )
    body = r2.json()
    assert body["audio_artifact_id"] == str(latest)
    assert body["fit_status"] == "ok"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


async def test_fit_check_unknown_job_404(app_under_test):
    r = await app_under_test.post(
        "/api/v1/audio/fit-check",
        json={"job_id": str(uuid.uuid4()), "target_duration_seconds": 30},
    )
    assert r.status_code == 404


async def test_fit_check_unknown_artifact_404(app_under_test):
    r = await app_under_test.post(
        "/api/v1/audio/fit-check",
        json={"audio_artifact_id": str(uuid.uuid4()), "target_duration_seconds": 30},
    )
    assert r.status_code == 404


async def test_fit_check_wrong_artifact_type_400(app_under_test):
    from app.core.db import get_sessionmaker
    from app.services import artifact_service

    sm = get_sessionmaker()
    async with sm() as session:
        art = await artifact_service.register_artifact(
            session,
            artifact_type="image",
            uri="file:///tmp/x.png",
            local_path="/tmp/x.png",
            mime_type="image/png",
            checksum_sha256="cafe" * 16,
            size_bytes=12,
        )
        await session.commit()
        art_id = art.id

    r = await app_under_test.post(
        "/api/v1/audio/fit-check",
        json={"audio_artifact_id": str(art_id), "target_duration_seconds": 30},
    )
    assert r.status_code == 400
    assert "expected 'audio'" in r.json()["detail"]


async def test_fit_check_requires_target_or_job(app_under_test):
    r = await app_under_test.post(
        "/api/v1/audio/fit-check",
        json={"audio_artifact_id": str(uuid.uuid4())},
    )
    assert r.status_code == 422  # caught by the model validator


# ---------------------------------------------------------------------------
# Edit-plan integration — editor stage embeds the fit verdict so the UI
# and downstream stages can read it without a live fit-check call.
# ---------------------------------------------------------------------------


def test_editor_embeds_fit_metadata_when_audio_duration_present():
    from agents.editor.handler import _build_edit_plan

    plan = _build_edit_plan(
        target_seconds=30.0,
        hook_text="Tip.",
        body_text="Body.",
        cta_text="CTA.",
        source_uri="s3://x/script.json",
        source_checksum="a" * 64,
        audio_duration_seconds=30.3,
    )
    md = plan.metadata
    assert md["fit_status"] == "ok"
    assert md["recommendation"] == "accept"
    assert md["audio_duration_seconds"] == 30.3
    assert md["duration_delta_seconds"] == 0.3


def test_editor_embeds_fit_metadata_when_audio_too_short():
    from agents.editor.handler import _build_edit_plan

    plan = _build_edit_plan(
        target_seconds=30.0,
        hook_text="x",
        body_text="x",
        cta_text="x",
        source_uri="s3://x/script.json",
        source_checksum="a" * 64,
        audio_duration_seconds=27.0,
    )
    md = plan.metadata
    assert md["fit_status"] == "too_short"
    assert md["recommendation"] == "regenerate_script_longer"
    assert md["duration_delta_seconds"] == -3.0


def test_editor_embeds_fit_metadata_when_audio_too_long():
    from agents.editor.handler import _build_edit_plan

    plan = _build_edit_plan(
        target_seconds=30.0,
        hook_text="x",
        body_text="x",
        cta_text="x",
        source_uri="s3://x/script.json",
        source_checksum="a" * 64,
        audio_duration_seconds=42.0,
    )
    md = plan.metadata
    assert md["fit_status"] == "too_long"
    assert md["recommendation"] == "adjust_target_duration"
    assert md["duration_delta_seconds"] == 12.0


def test_editor_embeds_missing_audio_when_no_duration_supplied():
    from agents.editor.handler import _build_edit_plan

    plan = _build_edit_plan(
        target_seconds=30.0,
        hook_text="x",
        body_text="x",
        cta_text="x",
        source_uri="s3://x/script.json",
        source_checksum="a" * 64,
        audio_duration_seconds=None,
    )
    md = plan.metadata
    assert md["fit_status"] == "missing_audio"
    assert md["recommendation"] == "upload_better_audio"
    assert md["audio_duration_seconds"] is None
    assert md["duration_delta_seconds"] is None


def test_editor_fit_windows_match_audio_fit_endpoint():
    """Sanity-pin the windows so the endpoint + handler can't drift."""
    from agents.editor.handler import (
        _FIT_OK_WINDOW_SECONDS,
        _FIT_SOFT_WINDOW_SECONDS,
    )
    from app.api.audio_fit import _OK_WINDOW_SECONDS, _SOFT_WINDOW_SECONDS

    assert _FIT_OK_WINDOW_SECONDS == _OK_WINDOW_SECONDS
    assert _FIT_SOFT_WINDOW_SECONDS == _SOFT_WINDOW_SECONDS
