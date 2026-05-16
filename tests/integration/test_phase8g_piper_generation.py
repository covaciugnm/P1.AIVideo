"""Phase 8G — Piper TTS generation (mocked + opt-in real smoke).

Phase 5A already wired the categorised 503 surface on
``/api/v1/tts/generate``. Phase 8G's contribution is:

- The Docker backend Dockerfile now accepts ``--build-arg INSTALL_PIPER=true``
  so operators can opt into the runtime without re-implementing the path.
- This test file pins the contract end-to-end: runtime-missing,
  assets-missing, mocked successful synthesis (via monkey-patching the
  Phase 5A PiperProvider so we don't depend on a real wheel), and the
  artifact-content endpoint serves the registered audio.
- An opt-in real smoke (``RUN_REAL_PIPER_SMOKE=1``) hits the live path
  when both runtime + voice assets are present.
"""
from __future__ import annotations

import io
import os
import wave
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def app_under_test(monkeypatch, tmp_path):
    audio_root = tmp_path / "audio"
    audio_root.mkdir()
    monkeypatch.setenv("UPLOAD_AUDIO_ROOT", str(audio_root))
    monkeypatch.setenv("UPLOAD_IMAGE_ROOT", str(tmp_path / "images"))
    monkeypatch.setenv("UPLOAD_TEXT_ROOT", str(tmp_path / "text"))
    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("SCRIPTWRITER_BACKEND", "template")
    monkeypatch.delenv("SCRIPTWRITER_ENABLE_NETWORK_CALLS", raising=False)

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
        yield client, audio_root, tmp_path
    await fake.aclose()
    queue_publisher.reset_redis_client()
    await core_db.async_reset_engine()


def _make_pcm_wav_bytes(duration_seconds: float = 0.3, sample_rate: int = 22050) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        frames = int(sample_rate * duration_seconds)
        w.writeframes(b"\x00\x00" * frames)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Runtime-missing branch (default state of the light backend)
# ---------------------------------------------------------------------------


async def test_tts_generate_runtime_missing_returns_503(app_under_test, monkeypatch):
    client, *_ = app_under_test

    # Mock _piper_runtime_available to False so we don't depend on the
    # actual import-spec presence.
    from app.api import tts as tts_mod

    monkeypatch.setattr(tts_mod, "_piper_runtime_available", lambda: False)

    r = await client.post(
        "/api/v1/tts/generate",
        json={"script_text": "hello", "tts_provider_id": "piper"},
    )
    assert r.status_code == 503
    body = r.json()
    assert body["detail"]["code"] == "tts_runtime_missing"


# ---------------------------------------------------------------------------
# Assets-missing branch
# ---------------------------------------------------------------------------


async def test_tts_generate_assets_missing_returns_503(app_under_test, monkeypatch):
    client, *_ = app_under_test
    from app.api import tts as tts_mod

    monkeypatch.setattr(tts_mod, "_piper_runtime_available", lambda: True)

    # Patch the agents.voice.providers.piper.provider.PiperProvider so
    # ``healthcheck`` returns missing_assets — no real piper wheel
    # needed.
    from common.enums import ProviderHealthStatus
    from common.schemas import ProviderHealth
    import agents.voice.providers.piper.provider as piper_mod

    class _FakePiper:
        def __init__(self) -> None:
            self._voice = "en_US-amy-medium"

        def healthcheck(self) -> ProviderHealth:
            return ProviderHealth(
                backend="piper",
                status=ProviderHealthStatus.missing_assets,
                missing_assets=["en_US-amy-medium.onnx", "en_US-amy-medium.onnx.json"],
                errors=["voices not found under PIPER_MODELS_ROOT"],
            )

        async def synthesize(self, *a, **k):  # noqa: ARG002 — unreachable
            raise RuntimeError("should not be called")

    monkeypatch.setattr(piper_mod, "PiperProvider", _FakePiper)

    r = await client.post(
        "/api/v1/tts/generate",
        json={"script_text": "hello", "tts_provider_id": "piper"},
    )
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "tts_assets_missing"


# ---------------------------------------------------------------------------
# Generation-failed branch — synthesize() raises
# ---------------------------------------------------------------------------


async def test_tts_generate_synthesize_raises_returns_failed(
    app_under_test, monkeypatch
):
    client, audio_root, _ = app_under_test
    from app.api import tts as tts_mod

    monkeypatch.setattr(tts_mod, "_piper_runtime_available", lambda: True)

    from common.enums import ProviderHealthStatus
    from common.schemas import ProviderHealth
    import agents.voice.providers.piper.provider as piper_mod

    class _BoomPiper:
        def __init__(self) -> None:
            self._voice = "en_US-amy-medium"

        def healthcheck(self) -> ProviderHealth:
            return ProviderHealth(
                backend="piper", status=ProviderHealthStatus.ok
            )

        async def synthesize(self, *a, **k):  # noqa: ARG002
            raise RuntimeError("synthetic boom")

    monkeypatch.setattr(piper_mod, "PiperProvider", _BoomPiper)

    r = await client.post(
        "/api/v1/tts/generate",
        json={"script_text": "hello", "tts_provider_id": "piper"},
    )
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "tts_generation_failed"


# ---------------------------------------------------------------------------
# Happy path — mocked successful synthesis → registered artifact
# ---------------------------------------------------------------------------


async def test_tts_generate_success_registers_audio_artifact(
    app_under_test, monkeypatch
):
    client, audio_root, _ = app_under_test
    from app.api import tts as tts_mod

    monkeypatch.setattr(tts_mod, "_piper_runtime_available", lambda: True)

    from common.enums import ProviderHealthStatus
    from common.schemas import ProviderHealth
    import agents.voice.providers.piper.provider as piper_mod

    class _FakeVoiceResult:
        def __init__(self, output_path: Path) -> None:
            self.output_path = str(output_path)

    class _FakePiper:
        def __init__(self) -> None:
            self._voice = "en_US-amy-medium"

        def healthcheck(self) -> ProviderHealth:
            return ProviderHealth(
                backend="piper", status=ProviderHealthStatus.ok
            )

        async def synthesize(self, req):
            # ``req.output_path`` is the controlled destination passed by
            # the API. Write a real PCM WAV there so the existing
            # Phase 3D validator + checksum + duration extraction work.
            output_path = Path(req.output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(_make_pcm_wav_bytes(duration_seconds=0.5))
            return _FakeVoiceResult(output_path)

    monkeypatch.setattr(piper_mod, "PiperProvider", _FakePiper)

    r = await client.post(
        "/api/v1/tts/generate",
        json={
            "script_text": "Phase 8G smoke test for Piper.",
            "tts_provider_id": "piper",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "generated"
    assert body["provider_id"] == "piper"
    assert body["mime_type"] == "audio/wav"
    assert body["duration_seconds"] > 0
    assert body["sample_rate"] == 22050
    assert body["channels"] == 1
    artifact_id = body["artifact_id"]

    # Round-trip via the Phase 8A artifact-content endpoint.
    content = await client.get(f"/api/v1/artifacts/{artifact_id}/content")
    assert content.status_code == 200
    assert content.headers["content-type"].startswith("audio/wav")
    assert len(content.content) > 0


# ---------------------------------------------------------------------------
# Module-load isolation: tts.py still doesn't pull torch / piper at load
# ---------------------------------------------------------------------------


def test_tts_api_module_has_no_torch_or_piper_at_load():
    import subprocess
    import sys

    code = (
        "import sys\n"
        "import app.api.tts  # noqa: F401\n"
        "leaked = [m for m in ('torch','piper','onnxruntime') if m in sys.modules]\n"
        "print(','.join(sorted(leaked)))\n"
    )
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=20,
        cwd=str(Path(__file__).resolve().parents[2]),
    )
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == ""


# ---------------------------------------------------------------------------
# Project invariants
# ---------------------------------------------------------------------------


def test_dockerfile_has_install_piper_build_arg():
    """Phase 8G shipped the opt-in via ``--build-arg INSTALL_PIPER=true``.
    Pin it so a future Dockerfile rewrite doesn't drop the switch."""
    src = (
        Path(__file__).resolve().parents[2]
        / "docker"
        / "backend"
        / "Dockerfile"
    ).read_text()
    assert "ARG INSTALL_PIPER=false" in src
    assert '"$INSTALL_PIPER" = "true"' in src or "$INSTALL_PIPER = true" in src
    assert "piper-tts" in src


def test_backend_pyproject_has_tts_extra():
    src = (
        Path(__file__).resolve().parents[2] / "backend" / "pyproject.toml"
    ).read_text()
    assert "[project.optional-dependencies]" in src
    assert "piper-tts" in src
    # And it lives in the ``tts`` extra, not the base ``dependencies``.
    base_block = src.split("[project.optional-dependencies]")[0]
    assert "piper-tts" not in base_block


# ---------------------------------------------------------------------------
# Optional real smoke — opt-in via RUN_REAL_PIPER_SMOKE=1
# ---------------------------------------------------------------------------


_REAL_SMOKE_ENABLED = os.environ.get("RUN_REAL_PIPER_SMOKE", "").lower() in (
    "1",
    "true",
    "yes",
    "on",
)


@pytest.mark.skipif(
    not _REAL_SMOKE_ENABLED,
    reason=(
        "Real Piper smoke disabled. Set RUN_REAL_PIPER_SMOKE=1 + "
        "PIPER_MODELS_ROOT pointing at on-disk .onnx + .onnx.json voice "
        "files + install ``piper-tts`` (or rebuild backend with "
        "--build-arg INSTALL_PIPER=true). See docs/runbooks/piper-runtime.md."
    ),
)
async def test_real_piper_smoke_when_explicitly_enabled(app_under_test):
    """Hit the real PiperProvider. Acceptable outcomes:
    - 201 with a populated WAV artifact (full success);
    - 503 ``tts_runtime_missing`` if the wheel still isn't on PATH;
    - 503 ``tts_assets_missing`` if voice files aren't in place."""
    client, *_ = app_under_test
    r = await client.post(
        "/api/v1/tts/generate",
        json={"script_text": "Real Piper smoke.", "tts_provider_id": "piper"},
    )
    assert r.status_code in (201, 503)
    if r.status_code == 503:
        assert r.json()["detail"]["code"] in (
            "tts_runtime_missing",
            "tts_assets_missing",
            "tts_provider_not_configured",
        )
    else:
        body = r.json()
        assert body["duration_seconds"] > 0
        assert body["sample_rate"] > 0


_ = Any  # placate unused-import linter
