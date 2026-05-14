"""Phase 5A — real Piper TTS runtime gating.

This file pins the **error categorisation** of /api/v1/tts/generate and
the corresponding /api/v1/providers/tts status. It does NOT exercise the
real piper-tts runtime — that would require an installed package + voice
files on disk + an explicit opt-in env var. Such a test would live next
to the existing Phase 3B Piper integration (which is already
skip-on-missing).
"""
from __future__ import annotations

import importlib.util

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def app_under_test(monkeypatch, tmp_path):
    # Reset Piper-related env so the runtime + assets are clearly missing.
    monkeypatch.delenv("PIPER_MODELS_ROOT", raising=False)
    monkeypatch.delenv("TTS_MODELS_ROOT", raising=False)
    monkeypatch.setenv("UPLOAD_AUDIO_ROOT", str(tmp_path / "audio"))
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


PIPER_INSTALLED = importlib.util.find_spec("piper") is not None


# ---------------------------------------------------------------------------
# /api/v1/tts/generate — categorised 503s
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    PIPER_INSTALLED,
    reason="piper-tts is installed — runtime-missing branch not testable here",
)
async def test_tts_generate_runtime_missing(app_under_test):
    r = await app_under_test.post(
        "/api/v1/tts/generate",
        json={"script_text": "hello world", "tts_provider_id": "piper"},
    )
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["code"] == "tts_runtime_missing"
    assert detail["provider_id"] == "piper"
    assert "piper-tts" in detail["message"]


@pytest.mark.skipif(
    not PIPER_INSTALLED,
    reason="piper-tts not installed — assets-missing branch only reachable with runtime",
)
async def test_tts_generate_assets_missing_when_root_unset(app_under_test):
    # Runtime present, but PIPER_MODELS_ROOT/TTS_MODELS_ROOT both unset.
    r = await app_under_test.post(
        "/api/v1/tts/generate",
        json={"script_text": "hello world", "tts_provider_id": "piper"},
    )
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["code"] == "tts_provider_not_configured"


async def test_tts_generate_unknown_provider_returns_not_implemented(app_under_test):
    r = await app_under_test.post(
        "/api/v1/tts/generate",
        json={"script_text": "hello", "tts_provider_id": "openai"},
    )
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["code"] == "tts_provider_not_implemented"
    assert detail["provider_id"] == "openai"


async def test_tts_generate_empty_script_rejected(app_under_test):
    r = await app_under_test.post(
        "/api/v1/tts/generate",
        json={"script_text": "", "tts_provider_id": "piper"},
    )
    assert r.status_code == 422


async def test_tts_generate_oversize_script_rejected(app_under_test):
    r = await app_under_test.post(
        "/api/v1/tts/generate",
        json={"script_text": "x" * 8001, "tts_provider_id": "piper"},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Provider metadata status reflects runtime/assets
# ---------------------------------------------------------------------------


async def test_providers_tts_status_when_runtime_missing(app_under_test):
    if PIPER_INSTALLED:
        pytest.skip("piper installed; this case checks the runtime-missing label")
    r = await app_under_test.get("/api/v1/providers/tts")
    assert r.status_code == 200
    body = r.json()
    piper = next(p for p in body if p["provider_id"] == "piper")
    assert piper["status"] == "not_configured"
    assert "piper-tts" in piper["notes"]


async def test_providers_tts_status_when_root_set_but_voice_missing(app_under_test, monkeypatch, tmp_path):
    if not PIPER_INSTALLED:
        pytest.skip("piper not installed; this case requires the runtime present")
    empty_root = tmp_path / "models"
    empty_root.mkdir()
    monkeypatch.setenv("PIPER_MODELS_ROOT", str(empty_root))
    monkeypatch.setenv("TTS_DEFAULT_VOICE", "en_US-test-medium")

    r = await app_under_test.get("/api/v1/providers/tts")
    assert r.status_code == 200
    piper = next(p for p in r.json() if p["provider_id"] == "piper")
    # Root set + runtime present but voice not on disk → "configured".
    assert piper["status"] == "configured"
    assert "Place" in piper["notes"] or "not found" in piper["notes"]


async def test_providers_tts_status_when_voice_present(app_under_test, monkeypatch, tmp_path):
    if not PIPER_INSTALLED:
        pytest.skip("piper not installed; this case requires the runtime present")
    models = tmp_path / "models"
    models.mkdir()
    (models / "en_US-test-medium.onnx").write_bytes(b"\x00")
    (models / "en_US-test-medium.onnx.json").write_text("{}")
    monkeypatch.setenv("PIPER_MODELS_ROOT", str(models))
    monkeypatch.setenv("TTS_DEFAULT_VOICE", "en_US-test-medium")

    r = await app_under_test.get("/api/v1/providers/tts")
    assert r.status_code == 200
    piper = next(p for p in r.json() if p["provider_id"] == "piper")
    assert piper["status"] == "available"


# ---------------------------------------------------------------------------
# No regressions / no secrets / no binary leaks
# ---------------------------------------------------------------------------


async def test_tts_generate_503_payload_carries_no_secret(app_under_test, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-tts-test")
    r = await app_under_test.post(
        "/api/v1/tts/generate",
        json={"script_text": "hello", "tts_provider_id": "piper"},
    )
    assert "sk-secret-tts-test" not in r.text


async def test_providers_tts_response_does_not_leak_paths(app_under_test, monkeypatch, tmp_path):
    # The path is operator-supplied (env), so it can appear in the notes — but
    # an unrelated secret never should.
    monkeypatch.setenv("PIPER_MODELS_ROOT", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-tts-secret")
    r = await app_under_test.get("/api/v1/providers/tts")
    assert "sk-tts-secret" not in r.text
