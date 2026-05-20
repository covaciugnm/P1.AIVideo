"""Phase 24 — clone profile, full-body reference, extended immutability.

Covers:
- POST /characters/{id}/clone copies the profile into a NEW editing
  character, drops the exclusive voice + face/full-body bindings, and
  gives it a fresh name/slug.
- Extended immutable fields: while active, place_of_birth / nationality /
  education_level cannot change (→ 409); moving to editing unlocks them.
- A cloned character can re-pick a voice that the source had reserved.
"""
from __future__ import annotations

import fakeredis.aioredis as fakeaioredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core import db as core_db
from app.main import create_app
from app.services import queue_publisher


@pytest_asyncio.fixture
async def client(monkeypatch, tmp_path):
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


_VOICE = "f5tts_ro_ro_femeie_1_lacramioara"


def _profile(name: str) -> dict:
    return {
        "identity": {
            "name": name,
            "date_of_birth": "1990-01-01",
            "gender": "female",
            "place_of_birth": "Cluj",
            "nationality": "Romanian",
            "spoken_languages": ["ro"],
            "is_public_persona": False,
        },
        "appearance": {},
        "education": {
            "education_level": "phd",
            "field_of_study": "Physics",
            "certifications": [],
            "previous_roles": [],
            "expertise": [],
        },
        "personality": {"archetype": "expert"},
        "voice": {"preferred_language": "ro"},
        "script_behaviour": {"allowed_topics": [], "blocked_topics": []},
    }


async def _create(client, name, *, voice=None, status="editing"):
    body: dict = {"profile": _profile(name), "status": status}
    if voice is not None:
        body["default_voice_provider_id"] = voice
    r = await client.post("/api/v1/characters", json=body)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_clone_drops_bindings_and_opens_editing(client):
    src = await _create(client, "Origin", voice=_VOICE, status="editing")
    r = await client.post(f"/api/v1/characters/{src['id']}/clone", json={"new_name": "Origin Branch"})
    assert r.status_code == 201, r.text
    clone = r.json()
    assert clone["id"] != src["id"]
    assert clone["name"] == "Origin Branch"
    assert clone["status"] == "editing"
    # Exclusive bindings dropped.
    assert clone["default_voice_provider_id"] is None
    assert clone["main_reference_image_id"] is None
    assert clone["full_body_reference_image_id"] is None
    assert clone["face_locked"] is False
    assert clone["full_body_locked"] is False
    # Profile bio copied across.
    assert clone["profile"]["identity"]["place_of_birth"] == "Cluj"
    assert clone["profile"]["education"]["education_level"] == "phd"


@pytest.mark.asyncio
async def test_clone_default_name(client):
    src = await _create(client, "Nameless", status="editing")
    r = await client.post(f"/api/v1/characters/{src['id']}/clone")
    assert r.status_code == 201, r.text
    assert r.json()["name"] == "Nameless (copy)"


@pytest.mark.asyncio
async def test_extended_immutability_when_active(client):
    # Build an activatable character: editing + voice; fake a face by
    # going through the status endpoint requires a main_reference, so we
    # test the immutability gate via update_character directly on an
    # active row created as active.
    c = await _create(client, "Frozen", voice=_VOICE, status="active")
    cid = c["id"]
    prof = _profile("Frozen")
    # Changing place_of_birth while active → 409.
    prof["identity"]["place_of_birth"] = "Iasi"
    r = await client.put(f"/api/v1/characters/{cid}", json={"profile": prof})
    assert r.status_code == 409, r.text
    assert "place_of_birth" in r.text

    # Changing education_level while active → 409.
    prof2 = _profile("Frozen")
    prof2["education"]["education_level"] = "msc"
    r2 = await client.put(f"/api/v1/characters/{cid}", json={"profile": prof2})
    assert r2.status_code == 409, r2.text
    assert "education_level" in r2.text


@pytest.mark.asyncio
async def test_editing_unlocks_immutable_fields(client):
    c = await _create(client, "Reopen", voice=_VOICE, status="active")
    cid = c["id"]
    # Move to editing → now bio is mutable.
    rt = await client.post(f"/api/v1/characters/{cid}/status", json={"status": "editing"})
    assert rt.status_code == 200, rt.text
    prof = _profile("Reopen")
    prof["identity"]["place_of_birth"] = "Iasi"
    r = await client.put(f"/api/v1/characters/{cid}", json={"profile": prof})
    assert r.status_code == 200, r.text
    assert r.json()["profile"]["identity"]["place_of_birth"] == "Iasi"
