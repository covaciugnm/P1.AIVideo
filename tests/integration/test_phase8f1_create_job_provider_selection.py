"""Phase 8F-1 — strict Create Job contract for ``provider_selection``.

Pins the contract end-to-end across every create / update / read
surface. Reproduces the Phase 8E ``extra_forbidden`` regression and
verifies the fix holds across:

- POST /api/v1/jobs                  (Phase 1)
- POST /api/v1/jobs/from-inputs      (Phase 4A-2; Phase 8E fix)
- POST /jobs                         (legacy mirror)
- PATCH /api/v1/jobs/{id}            (Phase 4E)
- GET /api/v1/jobs/{id}              (JobDetail)
- GET /api/v1/jobs                   (JobSummary list — Phase 8F-1 expose)
- GET /api/v1/jobs/{id}/summary      (JobFullSummary)

Required cases (spec §C):

1. POST /api/v1/jobs accepts full 8-key provider_selection.
2. POST /api/v1/jobs/from-inputs accepts full provider_selection.
3. Unknown / future provider IDs persist (Phase 6D contract).
4. Unknown extra key inside provider_selection → 422.
5. Job detail returns provider_selection.
6. Job summary endpoints expose provider_selection.
7. PATCH /jobs/{id} can update provider_selection.
8. ``extra_forbidden body.provider_selection`` regression pinned dead.
9. Legacy /jobs mirror keeps working.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def app_under_test(monkeypatch, tmp_path):
    monkeypatch.setenv("UPLOAD_AUDIO_ROOT", str(tmp_path / "audio"))
    monkeypatch.setenv("UPLOAD_IMAGE_ROOT", str(tmp_path / "images"))
    monkeypatch.setenv("UPLOAD_TEXT_ROOT", str(tmp_path / "text"))
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


_FULL_8 = {
    "script_provider_id": "template",
    "script_model": "template-v1",
    "tts_provider_id": "piper",
    "tts_model": "en_US-amy-medium",
    "video_provider_id": "sadtalker",
    "video_model": "sadtalker-v1",
    "audio_processor_id": "ffmpeg_convert",
    "image_processor_id": "stdlib_image_validation",
}


def _base_jobs_payload(provider_selection: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "brief": "Phase 8F-1 contract test",
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "target_duration_seconds": 30,
        "watermark_required": True,
        "c2pa_required": True,
        "voice_mode": "tts",
        "script_text": "hi",
    }
    if provider_selection is not None:
        body["provider_selection"] = provider_selection
    return body


def _base_from_inputs_payload(provider_selection: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "brief": "Phase 8F-1 from-inputs contract test",
        "target_duration_seconds": 30,
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "watermark_required": True,
        "c2pa_required": True,
        "voice_mode": "tts",
        "script_text": "hi",
    }
    if provider_selection is not None:
        body["provider_selection"] = provider_selection
    return body


# ---------------------------------------------------------------------------
# Case 1 — POST /api/v1/jobs accepts the full 8-key provider_selection
# ---------------------------------------------------------------------------


async def test_case1_jobs_accepts_full_provider_selection(app_under_test):
    r = await app_under_test.post(
        "/api/v1/jobs", json=_base_jobs_payload(_FULL_8)
    )
    assert r.status_code == 201, r.text
    assert r.json()["provider_selection"] == _FULL_8


# ---------------------------------------------------------------------------
# Case 2 — POST /api/v1/jobs/from-inputs accepts provider_selection
# ---------------------------------------------------------------------------


async def test_case2_from_inputs_accepts_full_provider_selection(app_under_test):
    r = await app_under_test.post(
        "/api/v1/jobs/from-inputs",
        json=_base_from_inputs_payload(_FULL_8),
    )
    assert r.status_code == 201, r.text
    assert r.json()["provider_selection"] == _FULL_8


# ---------------------------------------------------------------------------
# Case 3 — Unknown / future provider IDs persist (Phase 6D contract)
# ---------------------------------------------------------------------------


async def test_case3_unknown_future_provider_ids_persist(app_under_test):
    sel = {
        "script_provider_id": "custom_future_llm",
        "tts_provider_id": "custom_future_tts",
        "video_provider_id": "custom_future_video",
        "audio_processor_id": "custom_future_audio_processor",
        "image_processor_id": "custom_future_image_processor",
    }
    r = await app_under_test.post(
        "/api/v1/jobs/from-inputs", json=_base_from_inputs_payload(sel)
    )
    assert r.status_code == 201, r.text
    body = r.json()
    for k, v in sel.items():
        assert body["provider_selection"][k] == v


# ---------------------------------------------------------------------------
# Case 4 — Unknown extra key inside provider_selection → 422 (both endpoints)
# ---------------------------------------------------------------------------


async def test_case4_unknown_nested_key_rejected_on_jobs(app_under_test):
    r = await app_under_test.post(
        "/api/v1/jobs",
        json=_base_jobs_payload({"definitely_not_a_field": "x"}),
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    # The Pydantic loc must point at the nested unknown key — not the
    # provider_selection container itself.
    assert any(
        isinstance(item, dict)
        and item.get("type") == "extra_forbidden"
        and item.get("loc") == ["body", "provider_selection", "definitely_not_a_field"]
        for item in detail
    ), detail


async def test_case4_unknown_nested_key_rejected_on_from_inputs(app_under_test):
    r = await app_under_test.post(
        "/api/v1/jobs/from-inputs",
        json=_base_from_inputs_payload({"definitely_not_a_field": "x"}),
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert any(
        item.get("type") == "extra_forbidden"
        and item.get("loc") == ["body", "provider_selection", "definitely_not_a_field"]
        for item in detail
    ), detail


# ---------------------------------------------------------------------------
# Case 5 — GET /api/v1/jobs/{id} returns provider_selection (JobDetail)
# ---------------------------------------------------------------------------


async def test_case5_job_detail_returns_provider_selection(app_under_test):
    create = await app_under_test.post(
        "/api/v1/jobs/from-inputs", json=_base_from_inputs_payload(_FULL_8)
    )
    jid = create.json()["id"]
    detail = await app_under_test.get(f"/api/v1/jobs/{jid}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["provider_selection"] == _FULL_8


# ---------------------------------------------------------------------------
# Case 6 — Summary endpoints expose provider_selection
# ---------------------------------------------------------------------------


async def test_case6a_jobs_list_summary_includes_provider_selection(app_under_test):
    """Phase 8F-1 — JobSummary list rows now carry provider_selection."""
    create = await app_under_test.post(
        "/api/v1/jobs/from-inputs", json=_base_from_inputs_payload(_FULL_8)
    )
    jid = create.json()["id"]
    listed = await app_under_test.get("/api/v1/jobs")
    assert listed.status_code == 200, listed.text
    row = next((r for r in listed.json() if r["id"] == jid), None)
    assert row is not None, "newly-created job not in list"
    assert row["provider_selection"] == _FULL_8


async def test_case6b_full_summary_endpoint_returns_provider_selection(app_under_test):
    create = await app_under_test.post(
        "/api/v1/jobs/from-inputs", json=_base_from_inputs_payload(_FULL_8)
    )
    jid = create.json()["id"]
    summary = await app_under_test.get(f"/api/v1/jobs/{jid}/summary")
    assert summary.status_code == 200, summary.text
    assert summary.json()["job"]["provider_selection"] == _FULL_8


# ---------------------------------------------------------------------------
# Case 7 — PATCH /jobs/{id} can update provider_selection
# ---------------------------------------------------------------------------


async def test_case7_patch_can_update_provider_selection(app_under_test):
    create = await app_under_test.post(
        "/api/v1/jobs/from-inputs", json=_base_from_inputs_payload()
    )
    jid = create.json()["id"]
    new_sel = {
        "script_provider_id": "template",
        "tts_provider_id": "piper",
        "video_provider_id": "sadtalker",
        "audio_processor_id": "ffmpeg_convert",
        "image_processor_id": "stdlib_image_validation",
    }
    patch = await app_under_test.patch(
        f"/api/v1/jobs/{jid}", json={"provider_selection": new_sel}
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["provider_selection"] == new_sel
    # And the change persists on the next read.
    detail = await app_under_test.get(f"/api/v1/jobs/{jid}")
    assert detail.json()["provider_selection"] == new_sel


# ---------------------------------------------------------------------------
# Case 8 — extra_forbidden body.provider_selection regression pinned dead
# ---------------------------------------------------------------------------


async def test_case8_provider_selection_never_triggers_extra_forbidden(app_under_test):
    """Reproduces the exact Phase 8E user-reported error:

        {"type":"extra_forbidden","loc":["body","provider_selection"],
         "msg":"Extra inputs are not permitted","input":null}

    The fix is: ``provider_selection`` is a legitimate optional field
    on **both** create endpoints. Posting an object with
    ``provider_selection: null`` must NOT fail.
    """
    # Body uses provider_selection: null (the bug case — operator
    # didn't pick any provider, the frontend sends null).
    r = await app_under_test.post(
        "/api/v1/jobs/from-inputs",
        json={**_base_from_inputs_payload(), "provider_selection": None},
    )
    assert r.status_code == 201, r.text
    # Defensive: also check no error response anywhere contains the
    # specific loc tuple that caused the original bug.
    if r.status_code != 201:
        detail = r.json().get("detail", [])
        assert not any(
            isinstance(item, dict) and item.get("loc") == ["body", "provider_selection"]
            for item in detail
        ), "regression: extra_forbidden on provider_selection"


# ---------------------------------------------------------------------------
# Case 9 — Legacy /jobs mirror still works
# ---------------------------------------------------------------------------


async def test_case9a_legacy_jobs_mirror_accepts_provider_selection(app_under_test):
    """Phase 4B mounted the jobs router at both ``/jobs`` and
    ``/api/v1/jobs``. The legacy mount must keep accepting the same
    payload as the canonical one — otherwise older operator scripts
    break silently."""
    r = await app_under_test.post("/jobs", json=_base_jobs_payload(_FULL_8))
    assert r.status_code == 201, r.text
    assert r.json()["provider_selection"] == _FULL_8


async def test_case9b_legacy_from_inputs_does_not_exist(app_under_test):
    """The upload-intake / from-inputs router only mounts under
    ``/api/v1`` (Phase 4A-2). Legacy ``/jobs/from-inputs`` returns 405,
    not a regression — there's no legacy contract there to honour."""
    r = await app_under_test.post("/jobs/from-inputs", json=_base_from_inputs_payload())
    assert r.status_code in (404, 405)


# ---------------------------------------------------------------------------
# Provider-id values are not validated at write time (Phase 6D contract).
# Sanity-check the contract: a completely empty provider_selection dict
# round-trips as such.
# ---------------------------------------------------------------------------


async def test_empty_provider_selection_round_trips(app_under_test):
    """An empty ``provider_selection: {}`` must not crash. The
    backend coalesces all-None / empty selection to either ``{}`` or
    ``null`` on read — both are operationally equivalent and acceptable
    here; what matters is no 422 / 500."""
    r = await app_under_test.post(
        "/api/v1/jobs/from-inputs", json=_base_from_inputs_payload({})
    )
    assert r.status_code == 201, r.text
    assert r.json()["provider_selection"] in ({}, None)


# ---------------------------------------------------------------------------
# JobUpdateRequest also rejects unknown nested keys
# ---------------------------------------------------------------------------


async def test_patch_rejects_unknown_nested_provider_selection_key(app_under_test):
    create = await app_under_test.post(
        "/api/v1/jobs/from-inputs", json=_base_from_inputs_payload()
    )
    jid = create.json()["id"]
    patch = await app_under_test.patch(
        f"/api/v1/jobs/{jid}",
        json={"provider_selection": {"definitely_not_a_field": "x"}},
    )
    assert patch.status_code == 422


_ = uuid  # keep the import even if a future test removes the only use
