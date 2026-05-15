"""Phase 6C — Runtime readiness cross-cutting smoke.

These tests are **idempotent** regardless of whether Piper or Ollama is
installed on the test host. The default path:

1. Pin the provider catalog shape (every category, no secrets).
2. Pin the categorised 503 surface of /api/v1/tts/generate when Piper
   isn't installed.
3. Pin the categorised 503 surface of /api/v1/script/generate when
   network calls are disabled.
4. Pin that the orchestrator's stub providers never reach the network
   at module load (defensive — re-runs the Phase 3F import audit
   against the Phase 6C surface).
5. Pin that the public ``ALLOW_MODEL_AUTODOWNLOAD`` default stays
   ``false`` — the project never auto-downloads model weights.

Opt-in real-runtime tests guarded by env vars are documented at the
bottom; they're auto-skipped on a normal host.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def app_under_test(monkeypatch, tmp_path):
    monkeypatch.setenv("UPLOAD_AUDIO_ROOT", str(tmp_path / "audio"))
    monkeypatch.setenv("UPLOAD_IMAGE_ROOT", str(tmp_path / "images"))
    monkeypatch.setenv("UPLOAD_TEXT_ROOT", str(tmp_path / "text"))
    monkeypatch.setenv("PROVIDED_AUDIO_ALLOWED_ROOTS", str(tmp_path / "audio"))
    monkeypatch.setenv("PROVIDED_IMAGE_ALLOWED_ROOTS", str(tmp_path / "images"))
    # Make sure Ollama is the picked scriptwriter so the disabled-path
    # 503 hits even when defaults change.
    monkeypatch.setenv("SCRIPTWRITER_BACKEND", "template")
    monkeypatch.delenv("SCRIPTWRITER_ENABLE_NETWORK_CALLS", raising=False)
    monkeypatch.delenv("PIPER_MODELS_ROOT", raising=False)
    monkeypatch.delenv("TTS_MODELS_ROOT", raising=False)

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
# 1. Provider catalog shape
# ---------------------------------------------------------------------------


async def test_providers_catalog_lists_all_three_categories(app_under_test):
    r = await app_under_test.get("/api/v1/providers")
    assert r.status_code == 200
    body = r.json()
    # Phase 6D adds audio_processor + image_processor; the original
    # three keys remain.
    assert {"llm", "tts", "video_generator"}.issubset(set(body.keys()))
    assert len(body["llm"]) >= 1
    assert any(p["provider_id"] == "piper" for p in body["tts"])
    assert {"sadtalker", "musetalk", "wav2lip"}.issubset(
        {p["provider_id"] for p in body["video_generator"]}
    )


async def test_providers_catalog_does_not_leak_secrets(app_under_test, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-phase6c-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-phase6c-anthropic")
    r = await app_under_test.get("/api/v1/providers")
    text = r.text
    assert "sk-phase6c-secret" not in text
    assert "sk-phase6c-anthropic" not in text


async def test_providers_tts_status_includes_actionable_notes(app_under_test):
    r = await app_under_test.get("/api/v1/providers/tts")
    assert r.status_code == 200
    piper = next(p for p in r.json() if p["provider_id"] == "piper")
    # Either the runtime is missing → notes mention piper-tts, or the
    # root is unset → notes mention PIPER_MODELS_ROOT. In neither case
    # is the row left with empty notes.
    assert piper["notes"]
    assert ("piper-tts" in piper["notes"]) or ("PIPER_MODELS_ROOT" in piper["notes"])


async def test_providers_video_generators_all_not_implemented(app_under_test):
    r = await app_under_test.get("/api/v1/providers/video-generators")
    assert r.status_code == 200
    for p in r.json():
        assert p["status"] == "not_implemented"


# ---------------------------------------------------------------------------
# 2. TTS readiness — categorised 503
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    PIPER_INSTALLED,
    reason="piper-tts is installed — runtime_missing branch can't be tested here",
)
async def test_tts_generate_runtime_missing_without_piper(app_under_test):
    r = await app_under_test.post(
        "/api/v1/tts/generate",
        json={"script_text": "phase 6c smoke", "tts_provider_id": "piper"},
    )
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["code"] == "tts_runtime_missing"


@pytest.mark.skipif(
    not PIPER_INSTALLED,
    reason="piper-tts not installed — assets_missing path requires runtime",
)
async def test_tts_generate_assets_missing_with_runtime(app_under_test, monkeypatch, tmp_path):
    # Runtime is present (we landed in the skipif), root is set but the
    # voice file is absent → assets_missing.
    models = tmp_path / "models"
    models.mkdir()
    monkeypatch.setenv("PIPER_MODELS_ROOT", str(models))
    r = await app_under_test.post(
        "/api/v1/tts/generate",
        json={"script_text": "phase 6c smoke", "tts_provider_id": "piper"},
    )
    assert r.status_code == 503
    assert r.json()["detail"]["code"] in {"tts_assets_missing", "tts_provider_not_configured"}


# ---------------------------------------------------------------------------
# 3. Script readiness — categorised 503 + template fallback
# ---------------------------------------------------------------------------


async def test_script_generate_disabled_without_network_calls(app_under_test, monkeypatch):
    monkeypatch.setenv("SCRIPTWRITER_ENABLE_NETWORK_CALLS", "false")
    r = await app_under_test.post(
        "/api/v1/script/generate",
        json={
            "brief": "phase 6c readiness",
            "target_duration_seconds": 30,
            "provider_id": "ollama",
        },
    )
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["code"] == "script_provider_disabled"


async def test_script_generate_unreachable_with_network_calls_on_but_no_ollama(
    app_under_test, monkeypatch
):
    monkeypatch.setenv("SCRIPTWRITER_ENABLE_NETWORK_CALLS", "true")
    r = await app_under_test.post(
        "/api/v1/script/generate",
        json={
            "brief": "phase 6c readiness",
            "target_duration_seconds": 30,
            "provider_id": "ollama",
        },
    )
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "script_provider_unreachable"


async def test_script_generate_template_path_always_works(app_under_test):
    r = await app_under_test.post(
        "/api/v1/script/generate",
        json={
            "brief": "Three calming bedtime habits.",
            "target_duration_seconds": 30,
            "provider_id": "template",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "generated"
    assert body["provider_id"] == "template"
    assert body["hook"] and body["body"] and body["cta"]


# ---------------------------------------------------------------------------
# 4. No heavy / GPU imports at module load on the readiness paths
# ---------------------------------------------------------------------------


_FORBIDDEN_AT_IMPORT = (
    "torch",
    "torchvision",
    "torchaudio",
    "diffusers",
    "transformers",
    "accelerate",
    "xformers",
    "gfpgan",
    "sadtalker",
    "musetalk",
    "wav2lip",
    "openai",
    "anthropic",
    "httpx",
    "aiohttp",
)


def test_tts_module_loads_without_heavy_deps():
    """``app.api.tts`` is the endpoint code, not Piper itself. Importing
    it must not pull in torch / openai / etc., even though some of those
    are referenced by name inside conditional paths."""
    code = (
        "import sys, app.api.tts; "
        f"print([m for m in {_FORBIDDEN_AT_IMPORT!r} if m in sys.modules])"
    )
    res = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=20
    )
    assert res.returncode == 0, res.stderr
    leaked = res.stdout.strip()
    assert leaked == "[]", f"forbidden imports leaked at tts module load: {leaked}"


def test_script_module_loads_without_heavy_deps():
    code = (
        "import sys, app.api.script; "
        f"print([m for m in {_FORBIDDEN_AT_IMPORT!r} if m in sys.modules])"
    )
    res = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=20
    )
    assert res.returncode == 0, res.stderr
    leaked = res.stdout.strip()
    assert leaked == "[]", f"forbidden imports leaked at script module load: {leaked}"


def test_video_module_loads_without_heavy_deps():
    """The video contract endpoint must not import any ML runtime even
    by accident."""
    code = (
        "import sys, app.api.video; "
        f"print([m for m in {_FORBIDDEN_AT_IMPORT!r} if m in sys.modules])"
    )
    res = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=20
    )
    assert res.returncode == 0, res.stderr
    leaked = res.stdout.strip()
    assert leaked == "[]", f"forbidden imports leaked at video module load: {leaked}"


# ---------------------------------------------------------------------------
# 5. ALLOW_MODEL_AUTODOWNLOAD safety
# ---------------------------------------------------------------------------


def test_allow_model_autodownload_default_is_false():
    env_path = Path(__file__).resolve().parents[2] / ".env.example"
    text = env_path.read_text(encoding="utf-8")
    assert "ALLOW_MODEL_AUTODOWNLOAD=false" in text
    assert "ALLOW_MODEL_AUTODOWNLOAD=true" not in text


# ---------------------------------------------------------------------------
# 6. Optional real-runtime tests — auto-skip without explicit opt-in.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (
        PIPER_INSTALLED
        and os.environ.get("RUN_REAL_PIPER_SMOKE") == "1"
        and os.environ.get("PIPER_MODELS_ROOT")
    ),
    reason=(
        "Real Piper smoke disabled. Set RUN_REAL_PIPER_SMOKE=1 + "
        "PIPER_MODELS_ROOT + install piper-tts + place a voice on disk "
        "to enable."
    ),
)
async def test_real_piper_generation_smoke(app_under_test):
    r = await app_under_test.post(
        "/api/v1/tts/generate",
        json={
            "script_text": "Phase 6C real-runtime smoke.",
            "tts_provider_id": "piper",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "generated"
    assert body["mime_type"] == "audio/wav"
    assert body["duration_seconds"] > 0


@pytest.mark.skipif(
    os.environ.get("RUN_REAL_OLLAMA_SMOKE") != "1",
    reason=(
        "Real Ollama smoke disabled. Set RUN_REAL_OLLAMA_SMOKE=1 with a "
        "running ollama daemon + qwen3.6 model to enable."
    ),
)
async def test_real_ollama_generation_smoke(app_under_test, monkeypatch):
    monkeypatch.setenv("SCRIPTWRITER_ENABLE_NETWORK_CALLS", "true")
    monkeypatch.setenv("SCRIPTWRITER_BACKEND", "ollama")
    r = await app_under_test.post(
        "/api/v1/script/generate",
        json={
            "brief": "Three calming bedtime habits.",
            "target_duration_seconds": 30,
            "provider_id": "ollama",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "generated"
    assert body["provider_id"] == "ollama"
    assert body["full_script"]
