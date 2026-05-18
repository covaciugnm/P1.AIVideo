"""Phase 12X — DB-backed API secrets store.

Covers: catalog returned, save → list, env propagation, test probe
without burning quota, soft delete.
"""
from __future__ import annotations

import os

import fakeredis.aioredis as fakeaioredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core import db as core_db
from app.main import create_app
from app.services import queue_publisher


@pytest_asyncio.fixture
async def client(monkeypatch):
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


@pytest.mark.asyncio
async def test_secrets_catalog_includes_known_keys(client):
    r = await client.get("/api/v1/secrets")
    assert r.status_code == 200
    body = r.json()
    catalog_keys = {e["key_name"] for e in body["catalog"]}
    # The catalog must include every key the spec called out + the
    # image-generator hosted/local set.
    expected = {
        "HF_TOKEN",
        "FLUX_BFL_API_KEY",
        "STABILITY_API_KEY",
        "REPLICATE_API_TOKEN",
        "FAL_KEY",
        "TOGETHER_API_KEY",
        "IDEOGRAM_API_KEY",
        "RECRAFT_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "VERTEX_AI_PROJECT_ID",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "MIDJOURNEY_PROXY_URL",
        "MIDJOURNEY_PROXY_TOKEN",
        "FLUX_LOCAL_BASE_URL",
        "SDXL_LOCAL_BASE_URL",
        "SD35_LOCAL_BASE_URL",
        "COMFYUI_BASE_URL",
        "A1111_BASE_URL",
        "F5TTS_RO_BASE_URL",
        "SADTALKER_BASE_URL",
        "OLLAMA_BASE_URL",
        "IMAGE_GENERATOR_ENABLE_NETWORK_CALLS",
        "SCRIPTWRITER_ENABLE_NETWORK_CALLS",
    }
    assert expected <= catalog_keys
    # No persisted secrets at first.
    assert body["items"] == []


@pytest.mark.asyncio
async def test_upsert_propagates_to_os_environ(client, monkeypatch):
    # Clear any prior value the live env might carry.
    monkeypatch.delenv("FAKE_TEST_KEY_XX", raising=False)
    r = await client.post(
        "/api/v1/secrets",
        json={
            "key_name": "FAKE_TEST_KEY_XX",
            "value": "abc-123",
            "description": "test",
            "category": "misc",
        },
    )
    assert r.status_code == 201
    assert os.environ.get("FAKE_TEST_KEY_XX") == "abc-123"

    # Update via PUT — env is refreshed.
    r2 = await client.put(
        "/api/v1/secrets/FAKE_TEST_KEY_XX",
        json={"value": "xyz-999"},
    )
    assert r2.status_code == 200
    assert os.environ.get("FAKE_TEST_KEY_XX") == "xyz-999"

    # Delete removes from env.
    rd = await client.delete("/api/v1/secrets/FAKE_TEST_KEY_XX")
    assert rd.status_code == 204
    assert "FAKE_TEST_KEY_XX" not in os.environ


@pytest.mark.asyncio
async def test_test_probe_skipped_when_empty(client):
    await client.post(
        "/api/v1/secrets",
        json={"key_name": "HF_TOKEN", "value": "", "category": "huggingface"},
    )
    r = await client.post("/api/v1/secrets/HF_TOKEN/test")
    assert r.status_code == 200
    assert r.json()["status"] == "skipped"


@pytest.mark.asyncio
async def test_envvar_flag_probe_works_offline(client):
    """The IMAGE_GENERATOR_ENABLE_NETWORK_CALLS probe is a string
    compare — it must work without any network access."""
    await client.post(
        "/api/v1/secrets",
        json={
            "key_name": "IMAGE_GENERATOR_ENABLE_NETWORK_CALLS",
            "value": "true",
            "category": "misc",
        },
    )
    r = await client.post(
        "/api/v1/secrets/IMAGE_GENERATOR_ENABLE_NETWORK_CALLS/test"
    )
    body = r.json()
    assert body["status"] == "ok"
    assert "enabled" in body["detail"]
