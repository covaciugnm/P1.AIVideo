"""Phase 12 — Characters / Personas + image_generator registry.

Covers:
- ``image_generator`` category appears in /api/v1/providers with all 16
  providers (mock always available; FLUX local default ordering).
- Per-provider health-check endpoint persists overrides.
- CRUD on characters (create / list / get / update / delete-soft).
- Soft delete leaves the row + lets pre-existing snapshots survive.
- Editing a character does NOT mutate snapshots stored on jobs
  created before the edit.
- Character image library: mock provider generates a deterministic PNG;
  unconfigured providers return a categorised error.
- ``/api/v1/characters/:id/script-context`` returns localized
  paragraph-shaped briefing usable by the LLM scriptwriter.
- Job creation accepts ``character_id`` and persists the snapshot.
"""
from __future__ import annotations

import asyncio
import uuid

import fakeredis.aioredis as fakeaioredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core import db as core_db
from app.main import create_app
from app.services import queue_publisher


@pytest_asyncio.fixture
async def client(monkeypatch, tmp_path):
    # Phase 12 character images land under ARTIFACTS_LOCAL_ROOT/characters
    # — point it at a per-test tmp dir so we don't pollute the live tree.
    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path))
    await core_db.async_reset_engine()
    await core_db.init_db()
    fake = fakeaioredis.FakeRedis(decode_responses=True)
    queue_publisher.set_redis_client(fake)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await fake.aclose()
    queue_publisher.reset_redis_client()
    await core_db.async_reset_engine()


# ---------------------------------------------------------------------------
# Provider registry — image_generator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_providers_lists_image_generator_category(client):
    r = await client.get("/api/v1/providers")
    assert r.status_code == 200
    body = r.json()
    assert "image_generator" in body
    ids = [p["provider_id"] for p in body["image_generator"]]
    # 16 providers (1 mock + 5 local + 10 hosted).
    assert len(ids) == 16
    # Mock is always available + must appear in the catalog.
    assert "mock" in ids
    mock = next(p for p in body["image_generator"] if p["provider_id"] == "mock")
    assert mock["status"] == "available"
    # FLUX local default — first row when no IMAGE_GENERATOR_BACKEND override.
    assert body["image_generator"][0]["provider_id"] == "flux_local"


@pytest.mark.asyncio
async def test_image_generator_status_reflects_env(client, monkeypatch):
    # Without env vars, hosted APIs return not_configured.
    monkeypatch.delenv("FLUX_BFL_API_KEY", raising=False)
    r = await client.get("/api/v1/providers/image-generators")
    assert r.status_code == 200
    bfl = next(p for p in r.json() if p["provider_id"] == "flux_bfl_api")
    assert bfl["status"] == "not_configured"

    # With the env var, it flips to ``configured``.
    monkeypatch.setenv("FLUX_BFL_API_KEY", "fake-test-key")
    r2 = await client.get("/api/v1/providers/image-generators")
    bfl2 = next(p for p in r2.json() if p["provider_id"] == "flux_bfl_api")
    assert bfl2["status"] == "configured"


@pytest.mark.asyncio
async def test_provider_health_check_persists_override(client):
    r = await client.post("/api/v1/providers/image_generator/mock/health-check")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "available"
    # Hitting it again confirms persistence (table now has the row).
    r2 = await client.get("/api/v1/providers/image_generator/mock")
    assert r2.status_code == 200


# ---------------------------------------------------------------------------
# Characters CRUD + soft delete + version snapshots
# ---------------------------------------------------------------------------


def _minimal_profile(name: str = "Test Persona") -> dict:
    return {
        "identity": {
            "name": name,
            "spoken_languages": ["en"],
            "is_public_persona": False,
        },
        "appearance": {},
        "education": {"certifications": [], "previous_roles": [], "expertise": []},
        "personality": {"archetype": "expert"},
        "voice": {"preferred_language": "en"},
        "script_behaviour": {"allowed_topics": [], "blocked_topics": []},
    }


@pytest.mark.asyncio
async def test_character_crud_lifecycle(client):
    # Create.
    r = await client.post(
        "/api/v1/characters",
        json={"profile": _minimal_profile("Ada Lovelace"), "status": "active"},
    )
    assert r.status_code == 201, r.text
    created = r.json()
    cid = created["id"]
    assert created["name"] == "Ada Lovelace"
    assert created["slug"] == "ada-lovelace"
    assert created["version_number"] == 1
    assert created["status"] == "active"

    # List.
    rlist = await client.get("/api/v1/characters")
    assert rlist.status_code == 200
    assert any(c["id"] == cid for c in rlist.json()["items"])

    # Get.
    rget = await client.get(f"/api/v1/characters/{cid}")
    assert rget.status_code == 200
    assert rget.json()["profile"]["identity"]["name"] == "Ada Lovelace"

    # Update — bump archetype + add allowed topics.
    new_profile = _minimal_profile("Ada Lovelace")
    new_profile["personality"]["archetype"] = "teacher"
    new_profile["script_behaviour"]["allowed_topics"] = ["mathematics", "computing"]
    rup = await client.put(
        f"/api/v1/characters/{cid}",
        json={"profile": new_profile},
    )
    assert rup.status_code == 200, rup.text
    assert rup.json()["version_number"] == 2
    assert rup.json()["profile"]["personality"]["archetype"] == "teacher"

    # Soft delete.
    rdel = await client.delete(f"/api/v1/characters/{cid}")
    assert rdel.status_code == 200
    assert rdel.json()["status"] == "inactive"

    # List default hides soft-deleted.
    rlist2 = await client.get("/api/v1/characters")
    assert not any(c["id"] == cid for c in rlist2.json()["items"])

    # include_deleted=true reveals it again.
    rlist3 = await client.get("/api/v1/characters?include_deleted=true")
    assert any(c["id"] == cid for c in rlist3.json()["items"])


@pytest.mark.asyncio
async def test_character_unique_slug_collision(client):
    a = await client.post(
        "/api/v1/characters", json={"profile": _minimal_profile("Same Name")}
    )
    b = await client.post(
        "/api/v1/characters", json={"profile": _minimal_profile("Same Name")}
    )
    assert a.status_code == 201
    assert b.status_code == 201
    assert a.json()["slug"] != b.json()["slug"]
    assert b.json()["slug"].startswith("same-name-")


# ---------------------------------------------------------------------------
# Job snapshot preservation — editing a character does NOT mutate old jobs.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_editing_character_does_not_mutate_job_snapshot(client):
    cr = await client.post(
        "/api/v1/characters",
        json={"profile": _minimal_profile("Snapshot Persona")},
    )
    assert cr.status_code == 201
    cid = cr.json()["id"]

    # Create a job tied to the character.
    job_payload = {
        "brief": "Snapshot test brief — at least one full sentence.",
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "watermark_required": True,
        "c2pa_required": True,
        "target_duration_seconds": 30,
        "voice_mode": "tts",
        "script_text": "Hello world.",
        "tts_backend": "piper",
        "character_id": cid,
    }
    jr = await client.post("/api/v1/jobs", json=job_payload)
    assert jr.status_code == 201, jr.text
    job_id = jr.json()["id"]
    assert jr.json()["character_id"] == cid
    snapshot_v1 = jr.json()["character_snapshot"]
    assert snapshot_v1["personality"]["archetype"] == "expert"

    # Now mutate the character — change archetype to something completely
    # different. The pre-existing job's snapshot must be unchanged.
    new_profile = _minimal_profile("Snapshot Persona")
    new_profile["personality"]["archetype"] = "rebel"
    rup = await client.put(f"/api/v1/characters/{cid}", json={"profile": new_profile})
    assert rup.status_code == 200

    # Re-fetch the job — the snapshot must still be v1's archetype.
    jget = await client.get(f"/api/v1/jobs/{job_id}")
    assert jget.status_code == 200
    body = jget.json()
    assert body["character_snapshot"]["personality"]["archetype"] == "expert"

    # Soft-delete the character too. Job snapshot still intact.
    await client.delete(f"/api/v1/characters/{cid}")
    jget2 = await client.get(f"/api/v1/jobs/{job_id}")
    assert jget2.json()["character_snapshot"]["personality"]["archetype"] == "expert"


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_character_lookups_returns_bilingual_options(client):
    r = await client.get("/api/v1/characters/lookups")
    assert r.status_code == 200
    body = r.json()
    # Every standardised dropdown category present.
    for key in (
        "gender",
        "marital_status",
        "education_level",
        "personality_archetype",
        "communication_style",
        "narrative_role",
        "voice_gender",
        "image_status",
        "language",
    ):
        assert key in body and len(body[key]) >= 1
    # Each option carries bilingual labels + an i18n key.
    sample = body["gender"][0]
    assert {"value", "label_key", "label_en", "label_ro"} <= sample.keys()


# ---------------------------------------------------------------------------
# Script context builder (Phase D)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_character_script_context_paragraph_shape(client):
    profile = _minimal_profile("Context Persona")
    profile["personality"]["communication_style"] = "educational"
    profile["personality"]["narrative_role"] = "teacher"
    profile["education"]["education_level"] = "phd"
    profile["education"]["expertise"] = ["climate science", "policy"]
    profile["script_behaviour"]["blocked_topics"] = ["politics", "medical advice"]
    cr = await client.post("/api/v1/characters", json={"profile": profile})
    cid = cr.json()["id"]

    r = await client.get(f"/api/v1/characters/{cid}/script-context")
    assert r.status_code == 200
    body = r.json()
    text = body["text"]
    # Paragraph-shaped: markdown headers + bullet rows, NOT raw JSON.
    assert "## Character briefing" in text
    assert "Context Persona" in text
    # The standardised fields make it in.
    assert "phd" in text.lower()
    assert "educational" in text.lower()
    # Guard rails are surfaced explicitly so the LLM sees them in-prompt.
    assert "Blocked topics" in text
    assert "politics" in text


# ---------------------------------------------------------------------------
# Image library — mock provider end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_image_with_mock_provider(client):
    cr = await client.post("/api/v1/characters", json={"profile": _minimal_profile()})
    cid = cr.json()["id"]

    r = await client.post(
        f"/api/v1/characters/{cid}/images/generate",
        json={
            "prompt": "Portrait of a person, studio light",
            "provider_id": "mock",
            "seed": 42,
            "width": 256,
            "height": 256,
        },
    )
    assert r.status_code == 201, r.text
    img = r.json()
    assert img["provider_id"] == "mock"
    assert img["status"] == "draft"
    assert img["is_main_reference"] is False
    assert img["seed"] == 42
    assert img["width"] == 256 and img["height"] == 256
    assert img["checksum_sha256"]

    # The PNG is served back via the content endpoint.
    rc = await client.get(f"/api/v1/characters/{cid}/images/{img['id']}/content")
    assert rc.status_code == 200
    assert rc.headers["content-type"] == "image/png"
    assert rc.content[:8] == b"\x89PNG\r\n\x1a\n"

    # Determinism: same prompt + seed must yield the same checksum.
    r2 = await client.post(
        f"/api/v1/characters/{cid}/images/generate",
        json={
            "prompt": "Portrait of a person, studio light",
            "provider_id": "mock",
            "seed": 42,
            "width": 256,
            "height": 256,
        },
    )
    assert r2.json()["checksum_sha256"] == img["checksum_sha256"]


@pytest.mark.asyncio
async def test_unconfigured_provider_returns_categorised_error(client, monkeypatch):
    monkeypatch.delenv("FLUX_BFL_API_KEY", raising=False)
    cr = await client.post("/api/v1/characters", json={"profile": _minimal_profile()})
    cid = cr.json()["id"]

    r = await client.post(
        f"/api/v1/characters/{cid}/images/generate",
        json={"prompt": "hello", "provider_id": "flux_bfl_api"},
    )
    # HTTPException with structured detail.
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["error_code"] == "provider_not_configured"
    assert detail["provider_id"] == "flux_bfl_api"
    assert detail["fallback"] == "mock"


@pytest.mark.asyncio
async def test_local_wrapper_unconfigured_returns_error(client, monkeypatch):
    monkeypatch.delenv("FLUX_LOCAL_BASE_URL", raising=False)
    cr = await client.post("/api/v1/characters", json={"profile": _minimal_profile()})
    cid = cr.json()["id"]
    r = await client.post(
        f"/api/v1/characters/{cid}/images/generate",
        json={"prompt": "hello", "provider_id": "flux_local"},
    )
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["error_code"] == "provider_not_configured"


@pytest.mark.asyncio
async def test_accept_then_set_main_reference(client):
    cr = await client.post("/api/v1/characters", json={"profile": _minimal_profile()})
    cid = cr.json()["id"]
    g = await client.post(
        f"/api/v1/characters/{cid}/images/generate",
        json={"prompt": "headshot", "provider_id": "mock", "seed": 1},
    )
    img_id = g.json()["id"]

    a = await client.post(f"/api/v1/characters/{cid}/images/{img_id}/accept")
    assert a.status_code == 200
    # Phase 17F — first accept auto-promotes to main_reference, so the
    # service-side set_main_reference flips the status from "accepted"
    # to "reference" in the same response. ``image.is_main_reference``
    # is True straight from accept.
    assert a.json()["image"]["status"] in ("accepted", "reference")
    assert a.json()["image"]["is_main_reference"] is True
    assert a.json()["character_main_reference_image_id"] == img_id

    # Re-calling set-main-reference is idempotent on the already-promoted
    # image — the status stays "reference" and main_ref does not flip.
    s = await client.post(f"/api/v1/characters/{cid}/images/{img_id}/set-main-reference")
    assert s.status_code == 200
    body = s.json()
    assert body["image"]["is_main_reference"] is True
    assert body["image"]["status"] == "reference"
    assert body["character_main_reference_image_id"] == img_id

    # Character GET now exposes the reference.
    cg = await client.get(f"/api/v1/characters/{cid}")
    assert cg.json()["main_reference_image_id"] == img_id


@pytest.mark.asyncio
async def test_image_to_image_with_main_reference(client):
    cr = await client.post("/api/v1/characters", json={"profile": _minimal_profile()})
    cid = cr.json()["id"]
    g = await client.post(
        f"/api/v1/characters/{cid}/images/generate",
        json={"prompt": "p1", "provider_id": "mock", "seed": 1},
    )
    img_id = g.json()["id"]
    await client.post(f"/api/v1/characters/{cid}/images/{img_id}/set-main-reference")

    # Now a subsequent generate with use_main_reference must succeed via
    # the mock provider's image-to-image path.
    g2 = await client.post(
        f"/api/v1/characters/{cid}/images/generate",
        json={
            "prompt": "p2",
            "provider_id": "mock",
            "use_main_reference": True,
            "seed": 2,
        },
    )
    assert g2.status_code == 201, g2.text
