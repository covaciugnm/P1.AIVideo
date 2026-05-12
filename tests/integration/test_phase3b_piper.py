"""Phase 3B (narrow) integration tests — Piper-only.

Scope of these tests:

- Phase 3B implements ONE thing: the Piper TTS integration path with lazy
  imports and manual assets. This file pins the contract:

  1. The Piper provider module imports cleanly even when the ``piper``
     package isn't installed.
  2. ``synthesize()`` raises ``MissingAssetsError`` when assets are
     missing, regardless of whether ``piper`` is installed.
  3. ``synthesize()`` raises ``ProviderNotImplementedError`` when assets
     are present BUT ``piper`` is not installed — never reaches a Piper
     API call.
  4. Healthcheck always reports ``piper_runtime_installed`` in ``extra``.
  5. The end-to-end real-TTS path runs and produces a WAV — but only
     when both ``piper`` AND a real model directory are provided. Skipped
     otherwise so the test suite stays green in environments without
     either.

What we explicitly do NOT do here:
- No SadTalker work (still Phase 3A stub).
- No torch / diffusers / transformers / etc. dependencies.
- No model weights downloaded.
- No DAG wiring — the Phase 2 ``agents/voice/handler.py`` is still a no-op
  and the Phase 2 tests still cover its behavior.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from agents.voice.core.provider import VoiceRequest
from agents.voice.providers.piper.provider import (
    PiperProvider,
    _piper_runtime_available,
)
from common.enums import ProviderHealthStatus
from common.exceptions import MissingAssetsError, ProviderNotImplementedError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _piper_installed() -> bool:
    return importlib.util.find_spec("piper") is not None


def _stub_assets(provider: PiperProvider, root: Path) -> None:
    """Create empty files for each declared required asset."""
    for asset in provider.required_assets():
        full = root / asset.relative_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.touch()


@pytest.fixture
def isolated_env(monkeypatch):
    for var in ("PIPER_MODELS_ROOT", "TTS_MODELS_ROOT", "TTS_DEFAULT_VOICE"):
        monkeypatch.delenv(var, raising=False)
    yield monkeypatch


# ---------------------------------------------------------------------------
# Module import discipline
# ---------------------------------------------------------------------------


def test_provider_module_imports_cleanly_without_piper():
    """Importing ``agents.voice.providers.piper.provider`` MUST NOT
    transitively load the ``piper`` package or any TTS framework. We
    verify in a fresh subprocess so prior tests can't pollute sys.modules.
    """
    root = Path(__file__).resolve().parents[2]
    code = (
        "import sys\n"
        "from agents.voice.providers.piper.provider import PiperProvider\n"
        "PiperProvider()  # constructing must also stay light\n"
        "forbidden = ['piper', 'torch', 'torchvision', 'torchaudio',\n"
        "             'onnxruntime', 'transformers', 'diffusers']\n"
        "loaded = [m for m in forbidden if m in sys.modules]\n"
        "import json\n"
        "print(json.dumps(loaded))\n"
    )
    env = os.environ.copy()
    pp = env.get("PYTHONPATH", "")
    extras = [str(root), str(root / "backend")]
    env["PYTHONPATH"] = os.pathsep.join(extras + ([pp] if pp else []))
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(root),
        timeout=30,
    )
    assert result.returncode == 0, (
        f"subprocess failed:\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    loaded = json.loads(result.stdout.strip())
    assert loaded == [], f"Heavy modules transitively imported: {loaded}"


# ---------------------------------------------------------------------------
# Healthcheck reports runtime availability in `extra`
# ---------------------------------------------------------------------------


def test_healthcheck_reports_piper_runtime_in_extra(isolated_env, tmp_path):
    """Operators running an interactive healthcheck must see whether the
    Piper runtime is installed, alongside the asset status."""
    isolated_env.setenv("PIPER_MODELS_ROOT", str(tmp_path))
    health = PiperProvider().healthcheck()
    assert "piper_runtime_installed" in health.extra
    assert isinstance(health.extra["piper_runtime_installed"], bool)
    assert health.extra["piper_runtime_installed"] == _piper_runtime_available()


# ---------------------------------------------------------------------------
# Fail-fast: missing assets short-circuits BEFORE the lazy import
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_synthesize_missing_assets_short_circuits_before_lazy_import(
    isolated_env, tmp_path
):
    """``MissingAssetsError`` must fire before ``synthesize()`` ever
    reaches the lazy ``import piper`` line. This holds whether or not
    Piper is installed — the assets-check guards the integration path.
    """
    isolated_env.setenv("PIPER_MODELS_ROOT", str(tmp_path))
    # tmp_path is empty — no .onnx / .onnx.json present.
    provider = PiperProvider()
    req = VoiceRequest(
        job_id=uuid.uuid4(),
        text="hello",
        voice_id="en_US-amy-medium",
    )
    with pytest.raises(MissingAssetsError) as exc:
        await provider.synthesize(req)
    assert exc.value.backend == "piper"
    # Both files must show up in the error.
    assert any(p.endswith(".onnx") and not p.endswith(".onnx.json") for p in exc.value.missing)
    assert any(p.endswith(".onnx.json") for p in exc.value.missing)


# ---------------------------------------------------------------------------
# Fail-fast: piper not installed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.skipif(
    _piper_installed(),
    reason="piper installed; the real-TTS path is exercised by the integration test",
)
async def test_synthesize_refuses_when_piper_runtime_missing(isolated_env, tmp_path):
    """When asset files exist but ``piper`` isn't installed, synthesize
    must raise ``ProviderNotImplementedError`` with a clear, actionable
    message — and must NOT crash with an ``ImportError``."""
    isolated_env.setenv("PIPER_MODELS_ROOT", str(tmp_path))
    provider = PiperProvider()
    _stub_assets(provider, tmp_path)

    req = VoiceRequest(
        job_id=uuid.uuid4(),
        text="hello",
        voice_id="en_US-amy-medium",
    )
    with pytest.raises(ProviderNotImplementedError) as exc:
        await provider.synthesize(req)
    msg = str(exc.value)
    # Must mention the package name and how to install — actionable error.
    assert "piper" in msg.lower()
    assert "pip install" in msg.lower() or "piper-tts" in msg.lower()


# ---------------------------------------------------------------------------
# Real TTS — only runs when piper + real model dir are both available
# ---------------------------------------------------------------------------


def _real_piper_voice_dir() -> Path | None:
    """Return a directory containing a real Piper voice if the operator
    pointed us at one via ``PIPER_TEST_VOICE_ROOT``; else None.

    This is deliberately a separate env var from ``PIPER_MODELS_ROOT`` so
    a CI run setting the latter for healthcheck tests doesn't accidentally
    trigger the real-TTS test.
    """
    raw = os.environ.get("PIPER_TEST_VOICE_ROOT")
    if not raw:
        return None
    p = Path(raw)
    return p if p.is_dir() else None


@pytest.mark.asyncio
async def test_real_piper_synthesize_produces_wav(monkeypatch, tmp_path):
    """End-to-end Piper TTS smoke. Skipped unless BOTH:
      - the ``piper`` package is installed, AND
      - ``$PIPER_TEST_VOICE_ROOT`` points at a directory with a real
        voice (``<voice>.onnx`` + ``<voice>.onnx.json``).

    Without these, this test is informational only; it documents the
    integration without forcing weight downloads or heavy installs.
    """
    if not _piper_installed():
        pytest.skip("piper not installed; install `piper-tts` to run this test")
    voice_root = _real_piper_voice_dir()
    if voice_root is None:
        pytest.skip(
            "PIPER_TEST_VOICE_ROOT not set or not a directory; "
            "point it at a folder with a real Piper voice to run."
        )

    monkeypatch.setenv("PIPER_MODELS_ROOT", str(voice_root))
    # Auto-pick the first <voice>.onnx in the dir so the test isn't tied
    # to one specific voice id.
    onnx_files = sorted(voice_root.glob("*.onnx"))
    if not onnx_files:
        pytest.skip(f"no *.onnx files under {voice_root}")
    voice_id = onnx_files[0].stem
    monkeypatch.setenv("TTS_DEFAULT_VOICE", voice_id)

    provider = PiperProvider()
    health = provider.healthcheck()
    if health.status is not ProviderHealthStatus.ok:
        pytest.skip(f"piper provider not healthy: {health.errors}")

    output = tmp_path / "narration.wav"
    req = VoiceRequest(
        job_id=uuid.uuid4(),
        text="Three calming bedtime habits for better sleep.",
        voice_id=voice_id,
        output_path=str(output),
    )
    result = await provider.synthesize(req)

    assert output.exists()
    assert output.stat().st_size > 1000  # non-trivial WAV
    assert result.narration_uri.startswith("file://")
    assert result.duration_ms > 0
    assert result.sample_rate > 0
    assert result.voice_id == voice_id
