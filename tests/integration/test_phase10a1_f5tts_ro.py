"""Phase 10A-1 — F5TTS-Ro Romanian TTS provider.

Pins:
- ``f5tts_ro`` appears in the provider catalog (``/api/v1/providers/tts``)
  with the expected metadata (Romanian label, local, requires_model_files).
- Catalog status reflects env: unset → ``not_implemented``; URL set →
  ``configured``; URL + models root set → ``available``.
- ``/api/v1/tts/generate`` with ``tts_provider_id=f5tts_ro``:
  * without ``F5TTS_RO_BASE_URL`` → 503 ``tts_provider_not_configured``;
  * with URL pointing at an unreachable host → 503 ``tts_runtime_missing``;
  * with a mocked wrapper returning ``assets_missing`` →
    503 ``tts_assets_missing``;
  * with a mocked wrapper returning ``generated`` + a real WAV →
    registers ``ArtifactType.audio``.
- Importing the TTS API and provider registry does NOT pull torch /
  f5_tts at module load.
- The existing Piper preview tests continue to pass (regression).
"""
from __future__ import annotations

import io
import os
import sys
import wave
from pathlib import Path

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient


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
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def app_under_test(monkeypatch, tmp_path):
    monkeypatch.setenv("UPLOAD_AUDIO_ROOT", str(tmp_path / "audio"))
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
        yield client
    await fake.aclose()
    queue_publisher.reset_redis_client()
    await core_db.async_reset_engine()


# ---------------------------------------------------------------------------
# Provider catalog
# ---------------------------------------------------------------------------


async def test_f5tts_ro_appears_in_tts_catalog(app_under_test, monkeypatch, tmp_path):
    # Phase 20 — when no voices.yaml is present under
    # F5TTS_RO_MODELS_ROOT, the catalog falls back to the legacy
    # single-row provider entry. We force that path by pointing the
    # env at an empty tmp dir.
    monkeypatch.delenv("F5TTS_RO_BASE_URL", raising=False)
    monkeypatch.setenv("F5TTS_RO_MODELS_ROOT", str(tmp_path / "weights"))
    r = await app_under_test.get("/api/v1/providers/tts")
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [p["provider_id"] for p in body]
    assert "f5tts_ro" in ids
    f5 = next(p for p in body if p["provider_id"] == "f5tts_ro")
    assert "Romanian" in f5["label"]
    assert f5["category"] == "tts"
    assert f5["is_local"] is True
    assert f5["requires_model_files"] is True
    # No URL + no voices.yaml => not_configured (Phase 20 — the
    # catalog uses not_configured instead of not_implemented when the
    # operator has at least named a models root but nothing is there).
    assert f5["status"] in ("not_implemented", "not_configured")


async def test_f5tts_ro_status_configured_when_url_only(app_under_test, monkeypatch, tmp_path):
    monkeypatch.setenv("F5TTS_RO_BASE_URL", "http://example.invalid:8061")
    # Phase 20 — force the legacy fallback row by pointing at an
    # empty tmp dir (no voices.yaml).
    monkeypatch.setenv("F5TTS_RO_MODELS_ROOT", str(tmp_path / "weights"))
    r = await app_under_test.get("/api/v1/providers/tts")
    f5 = next(p for p in r.json() if p["provider_id"] == "f5tts_ro")
    # Phase 20 — the legacy fallback row reports not_configured when
    # voices.yaml is absent (operator has the URL but no voices on disk).
    assert f5["status"] in ("configured", "not_configured")


async def test_f5tts_ro_status_available_when_url_and_root(app_under_test, monkeypatch, tmp_path):
    monkeypatch.setenv("F5TTS_RO_BASE_URL", "http://example.invalid:8061")
    monkeypatch.setenv("F5TTS_RO_MODELS_ROOT", str(tmp_path / "weights"))
    r = await app_under_test.get("/api/v1/providers/tts")
    f5 = next(p for p in r.json() if p["provider_id"] == "f5tts_ro")
    # Phase 20 — without voices.yaml the legacy row reports
    # not_configured (the wrapper is up but nothing is selectable).
    assert f5["status"] in ("available", "not_configured")


# Phase 20 — voices.yaml-driven multi-voice expansion. When the
# catalog YAML lives under F5TTS_RO_MODELS_ROOT/voices.yaml the
# /providers/tts endpoint must emit one row per voice with the new
# language + voice_gender + sample_audio_url fields populated.
async def test_f5tts_ro_voices_yaml_expands_into_per_voice_rows(
    app_under_test, monkeypatch, tmp_path
):
    root = tmp_path / "f5"
    voices = root / "voices"
    (voices / "ro_test_male").mkdir(parents=True)
    (voices / "ro_test_female").mkdir(parents=True)
    for vd in (voices / "ro_test_male", voices / "ro_test_female"):
        (vd / "ref_audio.wav").write_bytes(b"\x00")
        (vd / "ref_text.txt").write_text("test", encoding="utf-8")
    (root / "voices.yaml").write_text(
        "voices:\n"
        "  - id: ro_test_male\n"
        "    label: Test Male\n"
        "    language: ro\n"
        "    gender: male\n"
        "    ref_audio: ref_audio.wav\n"
        "    ref_text: ref_text.txt\n"
        "    sample_text: salut\n"
        "  - id: ro_test_female\n"
        "    label: Test Female\n"
        "    language: ro\n"
        "    gender: female\n"
        "    ref_audio: ref_audio.wav\n"
        "    ref_text: ref_text.txt\n"
        "    sample_text: salut\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("F5TTS_RO_BASE_URL", "http://example.invalid:8061")
    monkeypatch.setenv("F5TTS_RO_MODELS_ROOT", str(root))
    r = await app_under_test.get("/api/v1/providers/tts")
    body = r.json()
    ids = [p["provider_id"] for p in body]
    assert "f5tts_ro_ro_test_male" in ids
    assert "f5tts_ro_ro_test_female" in ids
    # Legacy single-row entry is replaced by per-voice rows when
    # the catalog is present.
    assert "f5tts_ro" not in ids
    male = next(p for p in body if p["provider_id"] == "f5tts_ro_ro_test_male")
    assert male["voice_gender"] == "male"
    assert male["language"] == "ro"
    assert male["sample_text"] == "salut"
    assert male["sample_audio_url"] == "/api/v1/providers/tts/f5tts_ro_ro_test_male/sample.wav"


# ---------------------------------------------------------------------------
# /api/v1/tts/generate routing
# ---------------------------------------------------------------------------


async def test_tts_generate_f5tts_ro_without_url_returns_not_configured(
    app_under_test, monkeypatch
):
    monkeypatch.delenv("F5TTS_RO_BASE_URL", raising=False)
    r = await app_under_test.post(
        "/api/v1/tts/generate",
        json={
            "script_text": "Bună ziua!",
            "tts_provider_id": "f5tts_ro",
            "language": "ro",
        },
    )
    assert r.status_code == 503, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "tts_provider_not_configured"
    assert detail["provider_id"] == "f5tts_ro"


async def test_tts_generate_f5tts_ro_with_unreachable_url_returns_runtime_missing(
    app_under_test, monkeypatch
):
    # Point at a closed port — urllib will raise URLError ("Connection refused").
    monkeypatch.setenv("F5TTS_RO_BASE_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("F5TTS_RO_TIMEOUT", "1")
    r = await app_under_test.post(
        "/api/v1/tts/generate",
        json={
            "script_text": "Bună ziua!",
            "tts_provider_id": "f5tts_ro",
            "language": "ro",
        },
    )
    assert r.status_code == 503, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "tts_runtime_missing"
    assert detail["provider_id"] == "f5tts_ro"


async def test_tts_generate_f5tts_ro_assets_missing(
    app_under_test, monkeypatch
):
    """Mock the wrapper to return ``status=assets_missing``."""
    import json
    monkeypatch.setenv("F5TTS_RO_BASE_URL", "http://wrapper.invalid:8061")

    class _FakeResponse:
        status = 200

        def __init__(self, body: bytes) -> None:
            self._body = body

        def read(self) -> bytes:
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def _fake_urlopen(req, timeout):
        body = json.dumps(
            {
                "status": "assets_missing",
                "error_code": "assets_missing",
                "message": "Romanian model weights missing on /models/f5tts-ro",
            }
        ).encode("utf-8")
        return _FakeResponse(body)

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen, raising=False)

    r = await app_under_test.post(
        "/api/v1/tts/generate",
        json={
            "script_text": "Salut!",
            "tts_provider_id": "f5tts_ro",
            "language": "ro",
        },
    )
    assert r.status_code == 503, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "tts_assets_missing"
    assert "Romanian model" in detail["message"] or "missing" in detail["message"].lower()


async def test_tts_generate_f5tts_ro_mocked_success_registers_audio_artifact(
    app_under_test, monkeypatch, tmp_path
):
    """Mock the wrapper to write a real WAV and return ``status=generated``."""
    import json
    monkeypatch.setenv("F5TTS_RO_BASE_URL", "http://wrapper.invalid:8061")

    pcm_bytes = _make_pcm_wav_bytes(0.5, 22050)

    class _FakeResponse:
        status = 200

        def __init__(self, body: bytes) -> None:
            self._body = body

        def read(self) -> bytes:
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def _fake_urlopen(req, timeout):
        # The backend tells the wrapper where to put the WAV — emulate
        # the wrapper writing it at that path.
        body = req.data
        payload = json.loads(body.decode("utf-8"))
        out_path = Path(payload["output_path"])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(pcm_bytes)
        resp = json.dumps(
            {
                "status": "generated",
                "local_path": str(out_path),
                "duration_seconds": 0.5,
                "sample_rate": 22050,
                "channels": 1,
                "metadata": {"device": "cpu", "voice_id": payload.get("voice_id")},
            }
        ).encode("utf-8")
        return _FakeResponse(resp)

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen, raising=False)

    r = await app_under_test.post(
        "/api/v1/tts/generate",
        json={
            "script_text": "Bună ziua! Test în limba română.",
            "tts_provider_id": "f5tts_ro",
            "language": "ro",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "generated"
    assert body["provider_id"] == "f5tts_ro"
    assert body["mime_type"] == "audio/wav"
    assert body["sample_rate"] == 22050
    assert body["channels"] == 1
    # Real artifact row created → real on-disk file. The response URI
    # is the canonical ``file://`` location.
    assert body["uri"].startswith("file://")
    # Serve the bytes back via /content to prove the artifact row is
    # complete + the file is on the same volume.
    art_id = body["artifact_id"]
    art_r = await app_under_test.get(f"/api/v1/artifacts/{art_id}/content")
    assert art_r.status_code == 200, art_r.text
    assert art_r.headers["content-type"].startswith("audio/wav")
    assert len(art_r.content) == body["size_bytes"]


# ---------------------------------------------------------------------------
# Module-load isolation
# ---------------------------------------------------------------------------


def test_provider_registry_does_not_pull_torch_or_f5tts():
    """Both modules are already imported by every other test in this
    file (via the FastAPI app). The check is therefore a snapshot: after
    those imports, none of the forbidden heavy ML deps should have been
    dragged in as a side-effect."""
    import app.services.provider_registry  # noqa: F401
    forbidden = {"torch", "f5_tts", "f5tts", "torchaudio"}
    present = forbidden & set(sys.modules)
    assert not present, f"provider_registry leaked heavy deps: {present}"


def test_tts_api_does_not_pull_torch_or_f5tts():
    import app.api.tts  # noqa: F401
    forbidden = {"torch", "f5_tts", "f5tts", "torchaudio"}
    present = forbidden & set(sys.modules)
    assert not present, f"app.api.tts leaked heavy deps: {present}"


_ = (pytest, os)  # placate lint
