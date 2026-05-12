"""Phase 3A integration tests — provider contracts + healthchecks.

What we verify here:

- Each Phase-3A-implemented provider (SadTalker, Piper) declares its
  required assets, reports a structured ``ProviderHealth``, and refuses
  to run real inference.
- ``synthesize()`` fails fast on:
  - missing or invalid compliance token (LipSync only — token-gated),
  - missing assets on disk,
  - and finally raises ``ProviderNotImplementedError`` after both checks
    pass (real inference is deferred to Phase 3B).
- Placeholder providers (MuseTalk, Wav2Lip) report ``not_implemented``
  and never proceed.
- Importing any of the provider modules does NOT transitively load
  ``torch`` / ``diffusers`` / ``transformers`` / etc. — checked in a
  fresh subprocess so we don't get fooled by other tests' imports.

No model weights are downloaded, no media files are created.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agents.compliance_officer.compliance_token import mint_token
from agents.lipsync.core.provider import LipSyncRequest
from agents.lipsync.core.registry import resolve as resolve_lipsync
from agents.lipsync.providers.musetalk.provider import MuseTalkProvider
from agents.lipsync.providers.sadtalker.provider import SadTalkerProvider
from agents.lipsync.providers.wav2lip.provider import Wav2LipProvider
from agents.voice.core.provider import VoiceRequest
from agents.voice.core.registry import resolve as resolve_voice
from agents.voice.providers.piper.provider import PiperProvider
from common.enums import ProviderHealthStatus
from common.exceptions import (
    ComplianceTokenError,
    MissingAssetsError,
    ProviderNotImplementedError,
    UnsupportedBackendError,
)
from common.schemas import ComplianceTokenClaims


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_TEST_SIGNING_KEY = "phase3a-test-key-not-for-prod"


def _mint_valid_token(job_id: str, *, backend: str = "sadtalker") -> str:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    claims = ComplianceTokenClaims(
        job_id=job_id,
        synthetic_person_confirmed=True,
        consent_confirmed=True,
        watermark_required=True,
        c2pa_required=True,
        allowed_lipsync_backend=backend,
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )
    return mint_token(claims, _TEST_SIGNING_KEY)


def _stub_assets(provider, root: Path) -> None:
    """Create empty files for every declared required asset under root."""
    for asset in provider.required_assets():
        full = root / asset.relative_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.touch()


@pytest.fixture
def isolated_env(monkeypatch):
    """Strip every model-root env var so each test starts clean."""
    for var in (
        "SADTALKER_MODELS_ROOT",
        "LIPSYNC_MODELS_ROOT",
        "PIPER_MODELS_ROOT",
        "TTS_MODELS_ROOT",
        "COMPLIANCE_SIGNING_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    yield monkeypatch


# ---------------------------------------------------------------------------
# SadTalker healthcheck
# ---------------------------------------------------------------------------


def test_sadtalker_healthcheck_not_configured_when_env_missing(isolated_env):
    provider = SadTalkerProvider()
    health = provider.healthcheck()
    assert health.backend == "sadtalker"
    assert health.status is ProviderHealthStatus.not_configured
    assert health.errors


def test_sadtalker_healthcheck_missing_assets_for_empty_root(isolated_env, tmp_path):
    isolated_env.setenv("SADTALKER_MODELS_ROOT", str(tmp_path))
    provider = SadTalkerProvider()
    health = provider.healthcheck()
    assert health.status is ProviderHealthStatus.missing_assets
    assert health.models_root == str(tmp_path)
    # Every declared asset should be flagged.
    expected = {a.relative_path for a in provider.required_assets()}
    assert set(health.missing_assets) == expected


def test_sadtalker_healthcheck_falls_back_to_lipsync_models_root(
    isolated_env, tmp_path
):
    """SADTALKER_MODELS_ROOT unset, LIPSYNC_MODELS_ROOT set → use root/sadtalker."""
    isolated_env.setenv("LIPSYNC_MODELS_ROOT", str(tmp_path))
    provider = SadTalkerProvider()
    health = provider.healthcheck()
    # The resolved root should sit under tmp_path.
    assert health.models_root == str(tmp_path / "sadtalker")
    # Dir doesn't exist yet → all assets missing.
    assert health.status is ProviderHealthStatus.missing_assets


def test_sadtalker_healthcheck_ok_when_all_files_exist(isolated_env, tmp_path):
    isolated_env.setenv("SADTALKER_MODELS_ROOT", str(tmp_path))
    provider = SadTalkerProvider()
    _stub_assets(provider, tmp_path)
    health = provider.healthcheck()
    assert health.status is ProviderHealthStatus.ok
    assert health.missing_assets == []


# ---------------------------------------------------------------------------
# SadTalker synthesize — token first, then assets, then NotImplemented
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sadtalker_synthesize_refuses_invalid_token(isolated_env, tmp_path):
    """Even with all assets present, a bad token must short-circuit before
    any further work."""
    isolated_env.setenv("SADTALKER_MODELS_ROOT", str(tmp_path))
    isolated_env.setenv("COMPLIANCE_SIGNING_KEY", _TEST_SIGNING_KEY)
    provider = SadTalkerProvider()
    _stub_assets(provider, tmp_path)

    req = LipSyncRequest(
        job_id=uuid.uuid4(),
        portrait_uri="s3://bucket/portrait.png",
        audio_uri="s3://bucket/narration.wav",
        compliance_token="not-a-real-token.deadbeef",
    )
    with pytest.raises(ComplianceTokenError):
        await provider.synthesize(req)


@pytest.mark.asyncio
async def test_sadtalker_synthesize_refuses_when_signing_key_unset(
    isolated_env, tmp_path
):
    """Missing key must NOT be treated as 'any token is valid'."""
    isolated_env.setenv("SADTALKER_MODELS_ROOT", str(tmp_path))
    # signing key intentionally not set
    provider = SadTalkerProvider()
    _stub_assets(provider, tmp_path)

    req = LipSyncRequest(
        job_id=uuid.uuid4(),
        portrait_uri="s3://bucket/portrait.png",
        audio_uri="s3://bucket/narration.wav",
        compliance_token="anything",
    )
    with pytest.raises(ComplianceTokenError):
        await provider.synthesize(req)


@pytest.mark.asyncio
async def test_sadtalker_synthesize_refuses_when_assets_missing(
    isolated_env, tmp_path
):
    """Valid token + empty models_root → MissingAssetsError."""
    isolated_env.setenv("SADTALKER_MODELS_ROOT", str(tmp_path))
    isolated_env.setenv("COMPLIANCE_SIGNING_KEY", _TEST_SIGNING_KEY)
    provider = SadTalkerProvider()
    # tmp_path stays empty — no _stub_assets call.

    job_id = uuid.uuid4()
    token = _mint_valid_token(str(job_id))
    req = LipSyncRequest(
        job_id=job_id,
        portrait_uri="s3://bucket/portrait.png",
        audio_uri="s3://bucket/narration.wav",
        compliance_token=token,
    )
    with pytest.raises(MissingAssetsError) as exc:
        await provider.synthesize(req)
    assert exc.value.backend == "sadtalker"
    assert len(exc.value.missing) > 0


@pytest.mark.asyncio
async def test_sadtalker_synthesize_phase3a_does_not_run_inference(
    isolated_env, tmp_path
):
    """With token AND assets both OK, synthesize must STILL refuse to run
    inference in Phase 3A."""
    isolated_env.setenv("SADTALKER_MODELS_ROOT", str(tmp_path))
    isolated_env.setenv("COMPLIANCE_SIGNING_KEY", _TEST_SIGNING_KEY)
    provider = SadTalkerProvider()
    _stub_assets(provider, tmp_path)

    job_id = uuid.uuid4()
    token = _mint_valid_token(str(job_id))
    req = LipSyncRequest(
        job_id=job_id,
        portrait_uri="s3://bucket/portrait.png",
        audio_uri="s3://bucket/narration.wav",
        compliance_token=token,
    )
    with pytest.raises(ProviderNotImplementedError) as exc:
        await provider.synthesize(req)
    assert "Phase 3B" in str(exc.value)


# ---------------------------------------------------------------------------
# Placeholder providers
# ---------------------------------------------------------------------------


def test_musetalk_healthcheck_reports_not_implemented():
    health = MuseTalkProvider().healthcheck()
    assert health.backend == "musetalk"
    assert health.status is ProviderHealthStatus.not_implemented
    assert any("Phase 3B" in e or "v2" in e or "placeholder" in e for e in health.errors)


def test_wav2lip_healthcheck_reports_not_implemented():
    health = Wav2LipProvider().healthcheck()
    assert health.backend == "wav2lip"
    assert health.status is ProviderHealthStatus.not_implemented


@pytest.mark.asyncio
async def test_musetalk_synthesize_raises_not_implemented():
    req = LipSyncRequest(
        job_id=uuid.uuid4(),
        portrait_uri="s3://bucket/p.png",
        audio_uri="s3://bucket/a.wav",
        compliance_token="anything",
    )
    with pytest.raises(ProviderNotImplementedError):
        await MuseTalkProvider().synthesize(req)


@pytest.mark.asyncio
async def test_wav2lip_synthesize_raises_not_implemented():
    req = LipSyncRequest(
        job_id=uuid.uuid4(),
        portrait_uri="s3://bucket/p.png",
        audio_uri="s3://bucket/a.wav",
        compliance_token="anything",
    )
    with pytest.raises(ProviderNotImplementedError):
        await Wav2LipProvider().synthesize(req)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_lipsync_registry_resolves_known_backends():
    assert isinstance(resolve_lipsync("sadtalker"), SadTalkerProvider)
    assert isinstance(resolve_lipsync("musetalk"), MuseTalkProvider)
    assert isinstance(resolve_lipsync("wav2lip"), Wav2LipProvider)


def test_lipsync_registry_rejects_unknown_backend():
    with pytest.raises(UnsupportedBackendError):
        resolve_lipsync("totally-fake-backend")


def test_voice_registry_resolves_piper():
    assert isinstance(resolve_voice("piper"), PiperProvider)


def test_voice_registry_rejects_unknown_backend():
    with pytest.raises(UnsupportedBackendError):
        resolve_voice("totally-fake-tts")


# ---------------------------------------------------------------------------
# Piper healthcheck + fail-fast synthesize
# ---------------------------------------------------------------------------


def test_piper_healthcheck_not_configured_when_env_missing(isolated_env):
    provider = PiperProvider()
    health = provider.healthcheck()
    assert health.backend == "piper"
    assert health.status is ProviderHealthStatus.not_configured


def test_piper_healthcheck_missing_assets_for_empty_root(isolated_env, tmp_path):
    isolated_env.setenv("PIPER_MODELS_ROOT", str(tmp_path))
    provider = PiperProvider()
    health = provider.healthcheck()
    assert health.status is ProviderHealthStatus.missing_assets
    # Should flag both the .onnx and the .onnx.json file.
    assert any(p.endswith(".onnx") and not p.endswith(".onnx.json") for p in health.missing_assets)
    assert any(p.endswith(".onnx.json") for p in health.missing_assets)


def test_piper_healthcheck_falls_back_to_tts_models_root(isolated_env, tmp_path):
    isolated_env.setenv("TTS_MODELS_ROOT", str(tmp_path))
    provider = PiperProvider()
    health = provider.healthcheck()
    assert health.models_root == str(tmp_path / "piper")


def test_piper_healthcheck_ok_when_voice_files_present(isolated_env, tmp_path):
    isolated_env.setenv("PIPER_MODELS_ROOT", str(tmp_path))
    provider = PiperProvider()
    _stub_assets(provider, tmp_path)
    health = provider.healthcheck()
    assert health.status is ProviderHealthStatus.ok


@pytest.mark.asyncio
async def test_piper_synthesize_refuses_when_assets_missing(isolated_env, tmp_path):
    isolated_env.setenv("PIPER_MODELS_ROOT", str(tmp_path))
    provider = PiperProvider()  # tmp_path empty
    req = VoiceRequest(
        job_id=uuid.uuid4(),
        text="Three calming bedtime habits.",
        voice_id="en_US-amy-medium",
    )
    with pytest.raises(MissingAssetsError) as exc:
        await provider.synthesize(req)
    assert exc.value.backend == "piper"


@pytest.mark.asyncio
async def test_piper_synthesize_refuses_without_piper_runtime(isolated_env, tmp_path):
    """Piper provider's ``synthesize()`` must fail cleanly when the
    ``piper`` Python package isn't installed — even if asset files exist
    on disk. This pins the no-piper branch.

    When Piper IS installed, the real-TTS path activates and a different
    set of expectations applies (covered by
    ``tests/integration/test_phase3b_piper.py``); we skip here in that
    case so this test stays meaningful in either environment.
    """
    import importlib.util

    if importlib.util.find_spec("piper") is not None:
        pytest.skip("piper is installed; see test_phase3b_piper.py for the real-TTS path")

    isolated_env.setenv("PIPER_MODELS_ROOT", str(tmp_path))
    provider = PiperProvider()
    _stub_assets(provider, tmp_path)
    req = VoiceRequest(
        job_id=uuid.uuid4(),
        text="Three calming bedtime habits.",
        voice_id="en_US-amy-medium",
    )
    with pytest.raises(ProviderNotImplementedError) as exc:
        await provider.synthesize(req)
    assert "Phase 3B" in str(exc.value)


# ---------------------------------------------------------------------------
# No-heavy-imports invariant
# ---------------------------------------------------------------------------


def test_no_heavy_imports_when_loading_providers():
    """Importing the Phase 3A provider modules must NOT transitively load
    torch / diffusers / transformers / SadTalker / MuseTalk / piper. We
    verify in a fresh subprocess so we don't get fooled by modules already
    loaded by other tests in the same pytest session.
    """
    root = Path(__file__).resolve().parents[2]
    code = (
        "import sys\n"
        "from agents.lipsync.providers.sadtalker.provider import SadTalkerProvider\n"
        "from agents.lipsync.providers.musetalk.provider import MuseTalkProvider\n"
        "from agents.lipsync.providers.wav2lip.provider import Wav2LipProvider\n"
        "from agents.voice.providers.piper.provider import PiperProvider\n"
        "# Also exercise the registries (which lazy-import).\n"
        "from agents.lipsync.core.registry import resolve as r1\n"
        "from agents.voice.core.registry import resolve as r2\n"
        "r1('sadtalker'); r1('musetalk'); r1('wav2lip'); r2('piper')\n"
        "forbidden = ['torch', 'torchvision', 'torchaudio',\n"
        "             'transformers', 'diffusers', 'sadtalker',\n"
        "             'musetalk', 'wav2lip', 'piper', 'gfpgan']\n"
        "loaded = [m for m in forbidden if m in sys.modules]\n"
        "import json\n"
        "print(json.dumps(loaded))\n"
    )

    env = os.environ.copy()
    # Make `agents`, `common`, `app` importable in the subprocess regardless
    # of how the project is installed.
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
