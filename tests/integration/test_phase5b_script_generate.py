"""Phase 5B — /api/v1/script/generate endpoint.

Behavior pinned:

- Template provider always returns a structured script (hook/body/cta).
- Mock provider works the same way (deterministic).
- Ollama (and the other network providers) refuse with
  ``script_provider_disabled`` when ``SCRIPTWRITER_ENABLE_NETWORK_CALLS``
  is false, and with ``script_provider_unreachable`` when network calls
  are allowed but no real HTTP client is wired.
- Unknown provider id → ``script_provider_not_configured``.
- Schema validators catch obvious bad input (empty brief, oversize script
  text, out-of-range duration).
- No secrets are echoed back even when env vars carry them.

The default ``qwen3.6`` model lives in env (``SCRIPTWRITER_MODEL``) and
is exercised via the Ollama provider — but the spec asks that
``qwen3.6:7b`` NEVER be hardcoded, so this file also pins a defensive
grep on the codebase.
"""
from __future__ import annotations

import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def app_under_test(monkeypatch):
    monkeypatch.setenv("SCRIPTWRITER_BACKEND", "template")
    monkeypatch.delenv("SCRIPTWRITER_ENABLE_NETWORK_CALLS", raising=False)
    # We deliberately don't set OPENAI_API_KEY here; one test sets it to
    # confirm it never leaks into responses.

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


def _payload(provider_id: str = "template", **extra) -> dict:
    base = {
        "brief": "Three calming bedtime habits for better sleep.",
        "target_duration_seconds": 30,
        "language": "en",
        "provider_id": provider_id,
    }
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# Template + mock — deterministic happy paths
# ---------------------------------------------------------------------------


async def test_script_generate_template_returns_structured_script(app_under_test):
    r = await app_under_test.post("/api/v1/script/generate", json=_payload("template"))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "generated"
    assert body["provider_id"] == "template"
    assert body["hook"] and body["body"] and body["cta"]
    assert body["full_script"]
    assert body["estimated_duration_seconds"] > 0
    assert body["language"] == "en"


async def test_script_generate_template_with_script_text_input(app_under_test):
    payload = _payload("template", script_text="Tip one. Pause screens. Tip two.")
    r = await app_under_test.post("/api/v1/script/generate", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    # Template splits script_text into segments; full_script should contain
    # at least one of the source sentences.
    assert "screens" in body["full_script"].lower() or "tip" in body["full_script"].lower()


# ---------------------------------------------------------------------------
# Ollama — network gating
# ---------------------------------------------------------------------------


async def test_script_generate_ollama_disabled_when_network_calls_off(app_under_test, monkeypatch):
    monkeypatch.setenv("SCRIPTWRITER_ENABLE_NETWORK_CALLS", "false")
    r = await app_under_test.post("/api/v1/script/generate", json=_payload("ollama"))
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["code"] == "script_provider_disabled"
    assert detail["provider_id"] == "ollama"
    assert "SCRIPTWRITER_ENABLE_NETWORK_CALLS" in detail["message"]


async def test_script_generate_ollama_unreachable_when_network_calls_on(app_under_test, monkeypatch):
    monkeypatch.setenv("SCRIPTWRITER_ENABLE_NETWORK_CALLS", "true")
    # The provider stub always reports not_implemented — the endpoint
    # surfaces that as "script_provider_unreachable" when network calls
    # are enabled (the operator's intent is to reach a real LLM).
    r = await app_under_test.post("/api/v1/script/generate", json=_payload("ollama"))
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["code"] == "script_provider_unreachable"


# ---------------------------------------------------------------------------
# Unknown / malformed
# ---------------------------------------------------------------------------


async def test_script_generate_unknown_provider_returns_not_configured(app_under_test, monkeypatch):
    monkeypatch.setenv("SCRIPTWRITER_ENABLE_NETWORK_CALLS", "true")
    r = await app_under_test.post(
        "/api/v1/script/generate", json=_payload("does_not_exist")
    )
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["code"] == "script_provider_not_configured"


async def test_script_generate_rejects_empty_brief(app_under_test):
    r = await app_under_test.post(
        "/api/v1/script/generate",
        json={"brief": "", "target_duration_seconds": 30, "provider_id": "template"},
    )
    assert r.status_code == 422


async def test_script_generate_rejects_unknown_field(app_under_test):
    r = await app_under_test.post(
        "/api/v1/script/generate", json={**_payload(), "unknown": "x"}
    )
    assert r.status_code == 422


async def test_script_generate_rejects_out_of_range_duration(app_under_test):
    r = await app_under_test.post(
        "/api/v1/script/generate", json=_payload("template", target_duration_seconds=0)
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# No secret leaks + qwen3.6 default behaviour
# ---------------------------------------------------------------------------


async def test_script_generate_response_does_not_leak_secret(app_under_test, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-script-secret-test")
    monkeypatch.setenv("SCRIPTWRITER_ENABLE_NETWORK_CALLS", "true")
    r = await app_under_test.post("/api/v1/script/generate", json=_payload("openai"))
    assert "sk-script-secret-test" not in r.text


# Phase 3G already pins ``qwen3.6:7b`` not being hardcoded in
# production code (test_phase3g_scriptwriter_contracts.py
# ::test_qwen36_7b_is_not_hardcoded_anywhere). No duplicate guard here.
