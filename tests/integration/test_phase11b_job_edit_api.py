"""Phase 11B — PATCH /api/v1/jobs/{id} contract for the new
operator-facing edit flow.

What this phase pins beyond Phase 4E:

- ``provider_selection.*`` is patchable (single field or the full
  catalog) and the response surfaces the merged dict.
- Rejected / failed jobs are still editable on every Phase-11B field
  (provider_selection, voice_mode, video_language, subtitle_*, etc.)
  so the operator can fix a bad provider and re-run the DAG.
- Unknown nested keys under ``provider_selection`` produce 422.
- Invalid language / subtitle-format codes produce 422.
- Patching a published job is still 409 (hard terminal).
- Patching a non-existent job is 404.
- PATCH never auto-retries — it only mutates metadata. The
  ``recovery_metadata.retry_count`` only grows when POST /retry runs.
- Retry after edit: status flips back to ``pending_compliance`` and
  the response advertises ``can_retry=False`` (already re-queued).
- ``can_edit`` / ``can_retry`` / ``locked_fields`` on every GET +
  PATCH response.
"""
from __future__ import annotations

import uuid

import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


@pytest_asyncio.fixture
async def app_under_test(monkeypatch, tmp_path):
    monkeypatch.setenv("UPLOAD_AUDIO_ROOT", str(tmp_path / "audio"))
    monkeypatch.setenv("UPLOAD_IMAGE_ROOT", str(tmp_path / "images"))
    monkeypatch.setenv("UPLOAD_TEXT_ROOT", str(tmp_path / "text"))
    monkeypatch.setenv("PROVIDED_AUDIO_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("PROVIDED_IMAGE_ALLOWED_ROOTS", str(tmp_path))
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


async def _create_job(
    client: AsyncClient,
    *,
    brief: str = "phase 11b",
    provider_selection: dict | None = None,
) -> str:
    payload: dict = {
        "brief": brief,
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "target_duration_seconds": 30,
        "watermark_required": True,
        "c2pa_required": True,
        "script_text": "phase 11b script",
    }
    if provider_selection is not None:
        payload["provider_selection"] = provider_selection
    r = await client.post("/api/v1/jobs", json=payload)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _force_job_status(job_id: str, status: str) -> None:
    """Flip a job into a terminal/intermediate status directly via the DB
    so the test doesn't have to drive the DAG to get a rejected row."""
    from app.core.db import get_sessionmaker
    from app.models.job import Job, JobStatus

    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(select(Job).where(Job.id == uuid.UUID(job_id)))
        job = result.scalar_one()
        job.status = JobStatus(status)
        if status in ("rejected", "failed"):
            job.rejection_reason = (
                "tts_provider_not_configured: only 'piper' is wired in this "
                "DAG; selected provider 'custom_future_tts' has no DAG adapter."
            )
        await session.commit()


# ---------------------------------------------------------------------------
# Happy-path edits
# ---------------------------------------------------------------------------


async def test_patch_brief_updates_field(app_under_test):
    """1. PATCH existing job updates brief."""
    job_id = await _create_job(app_under_test)
    r = await app_under_test.patch(
        f"/api/v1/jobs/{job_id}", json={"brief": "edited brief 11b"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["brief"] == "edited brief 11b"
    assert body["can_edit"] is True
    assert body["can_retry"] is False
    assert body["locked_fields"] == []


async def test_patch_updates_single_provider_selection_field(app_under_test):
    """2. PATCH updates provider_selection.tts_provider_id."""
    job_id = await _create_job(
        app_under_test,
        provider_selection={"tts_provider_id": "custom_future_tts"},
    )
    r = await app_under_test.patch(
        f"/api/v1/jobs/{job_id}",
        json={"provider_selection": {"tts_provider_id": "piper"}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider_selection"]["tts_provider_id"] == "piper"


async def test_patch_updates_all_provider_selection_fields(app_under_test):
    """3. PATCH updates every provider_selection slot (5 categories)."""
    job_id = await _create_job(app_under_test)
    selection = {
        "script_provider_id": "template",
        "script_model": "template-default",
        "tts_provider_id": "piper",
        "tts_model": "ro_RO-mihai-medium",
        "video_provider_id": "sadtalker",
        "video_model": "sadtalker-default",
        "audio_processor_id": "ffmpeg_convert",
        "image_processor_id": "stdlib_image_validation",
    }
    r = await app_under_test.patch(
        f"/api/v1/jobs/{job_id}", json={"provider_selection": selection}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    for key, value in selection.items():
        assert body["provider_selection"][key] == value, key


async def test_patch_rejected_job_changes_tts_provider(app_under_test):
    """4. PATCH rejected job from custom_future_tts to piper.

    This is the user's headline Phase 11B scenario: the voice stage
    rejected because the operator picked a metadata-only provider, and
    the dashboard must let them fix it without creating a new job.
    """
    job_id = await _create_job(
        app_under_test,
        provider_selection={
            "tts_provider_id": "custom_future_tts",
            "script_provider_id": "template",
            "video_provider_id": "sadtalker",
        },
    )
    await _force_job_status(job_id, "rejected")

    r = await app_under_test.patch(
        f"/api/v1/jobs/{job_id}",
        json={"provider_selection": {"tts_provider_id": "piper"}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "rejected"  # still rejected; user must Retry
    assert body["provider_selection"]["tts_provider_id"] == "piper"
    assert body["can_edit"] is True
    assert body["can_retry"] is True


async def test_patch_unknown_nested_provider_key_returns_422(app_under_test):
    """5. PATCH unknown nested provider key returns 422.

    ProviderSelection has ``extra="forbid"`` — typo'd or
    non-canonical keys must surface as validation errors so the UI can
    show the operator the exact field that's wrong.
    """
    job_id = await _create_job(app_under_test)
    r = await app_under_test.patch(
        f"/api/v1/jobs/{job_id}",
        json={"provider_selection": {"tts_provider_idd": "piper"}},
    )
    assert r.status_code == 422, r.text


async def test_patch_unknown_job_returns_404(app_under_test):
    """6. PATCH unknown job returns 404."""
    missing = uuid.uuid4()
    r = await app_under_test.patch(
        f"/api/v1/jobs/{missing}", json={"brief": "irrelevant"}
    )
    assert r.status_code == 404


async def test_patch_invalid_language_returns_422(app_under_test):
    """7. PATCH invalid language returns 422."""
    job_id = await _create_job(app_under_test)
    r = await app_under_test.patch(
        f"/api/v1/jobs/{job_id}", json={"video_language": "not-a-language"}
    )
    assert r.status_code == 422


async def test_patch_subtitle_settings_persists(app_under_test):
    """8. PATCH subtitle settings persists end-to-end."""
    job_id = await _create_job(app_under_test)
    r = await app_under_test.patch(
        f"/api/v1/jobs/{job_id}",
        json={
            "subtitle_enabled": True,
            "subtitle_languages": ["ro", "en"],
            "subtitle_format": "vtt",
            "subtitle_burn_in": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["subtitle_enabled"] is True
    assert body["subtitle_languages"] == ["ro", "en"]
    assert body["subtitle_format"] == "vtt"

    # Confirm the persisted row exposes the same values on a fresh GET.
    fresh = await app_under_test.get(f"/api/v1/jobs/{job_id}")
    assert fresh.status_code == 200
    fb = fresh.json()
    assert fb["subtitle_enabled"] is True
    assert fb["subtitle_languages"] == ["ro", "en"]
    assert fb["subtitle_format"] == "vtt"


async def test_patch_published_job_rejects_with_409(app_under_test):
    """9. PATCH published job rejects locked-field mutation (409)."""
    job_id = await _create_job(app_under_test)
    await _force_job_status(job_id, "published")

    # Brief is normally pre-terminal-editable, but a published job is
    # fully locked.
    r = await app_under_test.patch(
        f"/api/v1/jobs/{job_id}", json={"brief": "should not apply"}
    )
    assert r.status_code == 409, r.text

    # The GET response advertises the locked fields so the UI can render
    # a disabled form.
    fresh = (await app_under_test.get(f"/api/v1/jobs/{job_id}")).json()
    assert fresh["can_edit"] is False
    assert fresh["can_retry"] is False
    assert "brief" in fresh["locked_fields"]
    assert "provider_selection" in fresh["locked_fields"]


async def test_patch_does_not_auto_retry(app_under_test):
    """10. PATCH does not auto-retry the job.

    Editing a rejected job leaves it in ``rejected`` — only POST /retry
    re-queues it. recovery_metadata.retry_count must stay at 0 until the
    operator explicitly hits Retry.
    """
    job_id = await _create_job(
        app_under_test,
        provider_selection={"tts_provider_id": "custom_future_tts"},
    )
    await _force_job_status(job_id, "rejected")

    r = await app_under_test.patch(
        f"/api/v1/jobs/{job_id}",
        json={"provider_selection": {"tts_provider_id": "piper"}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "rejected"
    rm = body.get("recovery_metadata") or {}
    assert int(rm.get("retry_count", 0)) == 0


async def test_retry_after_edit_requeues_job(app_under_test):
    """11. Retry after edit works: PATCH then /retry → pending_compliance.

    The scenario the operator runs end-to-end: fix the bad provider
    via PATCH, click Retry, and the orchestrator can pick the row up
    again on the next poll cycle.
    """
    job_id = await _create_job(
        app_under_test,
        provider_selection={"tts_provider_id": "custom_future_tts"},
    )
    await _force_job_status(job_id, "rejected")

    patch_r = await app_under_test.patch(
        f"/api/v1/jobs/{job_id}",
        json={"provider_selection": {"tts_provider_id": "piper"}},
    )
    assert patch_r.status_code == 200

    retry_r = await app_under_test.post(
        f"/api/v1/jobs/{job_id}/retry",
        json={"reason": "patched provider; re-running"},
    )
    assert retry_r.status_code == 200, retry_r.text
    rb = retry_r.json()
    # Phase 11B contract: retry flips the status back so the worker
    # picks the patched job up again.
    assert rb["status"] == "pending_compliance"
    assert rb["rejection_reason"] in (None, "")
    assert rb["provider_selection"]["tts_provider_id"] == "piper"
    rm = rb["recovery_metadata"]
    assert rm["retry_count"] == 1
    assert "retry_requested_at" in rm
    # Now the job is re-queued, so the policy says no second retry
    # (would be a no-op until it terminates again).
    assert rb["can_retry"] is False
    assert rb["can_edit"] is True
