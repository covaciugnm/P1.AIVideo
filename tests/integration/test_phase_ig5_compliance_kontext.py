"""Phase IG-5 — gated upload-reference + moderation gate + Kontext stub."""
from __future__ import annotations

import io

import fakeredis.aioredis as fakeaioredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core import db as core_db
from app.main import create_app
from app.services import queue_publisher
from app.services.image_providers import get_image_provider
from app.services.image_providers.base import (
    ImageGenerationInput,
    ProviderUnavailableError,
)

_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00"
    b"\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


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


def _profile(name):
    return {
        "identity": {"name": name, "gender": "female", "is_public_persona": False,
                     "spoken_languages": ["ro"]},
        "appearance": {}, "education": {"certifications": [], "previous_roles": [], "expertise": []},
        "personality": {}, "voice": {}, "script_behaviour": {"allowed_topics": [], "blocked_topics": []},
    }


async def _create(client, name):
    r = await client.post("/api/v1/characters", json={"profile": _profile(name), "status": "editing"})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_upload_without_attestation_blocked(client):
    c = await _create(client, "Up1")
    r = await client.post(
        f"/api/v1/characters/{c['id']}/images/upload-reference",
        files={"file": ("ref.png", io.BytesIO(_PNG), "image/png")},
        data={"synthetic_attestation": "false"},
    )
    assert r.status_code == 422, r.text
    assert "attestation" in r.text.lower()


@pytest.mark.asyncio
async def test_upload_with_attestation_pending_then_moderation_gates_canonical(client):
    c = await _create(client, "Up2")
    cid = c["id"]
    # Upload with attestation → pending moderation.
    r = await client.post(
        f"/api/v1/characters/{cid}/images/upload-reference",
        files={"file": ("ref.png", io.BytesIO(_PNG), "image/png")},
        data={"synthetic_attestation": "true"},
    )
    assert r.status_code == 200, r.text
    img = r.json()
    assert img["generation_params_json"]["moderation_status"] == "pending"
    iid = img["id"]

    # Promotion blocked while pending.
    r2 = await client.post(
        f"/api/v1/characters/{cid}/images/{iid}/set-main-reference"
    )
    assert r2.status_code == 409, r2.text
    assert "moderation" in r2.text.lower()

    # Approve, then promotion works.
    r3 = await client.post(
        f"/api/v1/characters/{cid}/images/{iid}/moderate",
        data={"decision": "approve"},
    )
    assert r3.status_code == 200, r3.text
    r4 = await client.post(
        f"/api/v1/characters/{cid}/images/{iid}/set-main-reference"
    )
    assert r4.status_code == 200, r4.text
    assert r4.json()["character_main_reference_image_id"] == iid


@pytest.mark.asyncio
async def test_kontext_stub_fails_clearly():
    prov = get_image_provider("flux_kontext")
    health = await prov.health_check()
    assert health.status == "not_configured"
    inp = ImageGenerationInput(
        prompt="edit", negative_prompt=None, model_id=None, seed=1,
        width=512, height=512, steps=10, guidance_scale=3.0,
        reference_image_path="/tmp/x.png",
    )
    with pytest.raises(ProviderUnavailableError) as ei:
        await prov.generate_image_to_image(inp)
    assert ei.value.error_code == "provider_not_configured"


@pytest.mark.asyncio
async def test_face_score_disabled_returns_null(monkeypatch):
    monkeypatch.setenv("FACE_EMBEDDING_ENABLED", "false")
    from app.services import image_face_score
    score, drift = image_face_score.score_identity("/a.png", "/b.png")
    assert score is None and drift is False
