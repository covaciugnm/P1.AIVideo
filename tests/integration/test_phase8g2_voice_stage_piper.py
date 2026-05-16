"""Phase 8G-2 — DAG voice stage now calls real PiperProvider.

Replaces the Phase 3D ``_run_tts_noop`` stub for ``voice_mode="tts"``
with provider-aware routing that:

1. Reads ``state.provider_selection["tts_provider_id"]`` /
   ``state.tts_backend`` to resolve the TTS provider.
2. For ``piper``: probes runtime + healthcheck, then either calls
   real ``synthesize()`` or raises a categorised ``StageRejection``.
3. Falls back to a clearly-categorised placeholder ``StageOutput``
   (with ``extra.real_tts=False``) when the operator hasn't explicitly
   opted in to Piper AND the runtime isn't installed — preserves
   Phase 2/3 metadata-only end-to-end test invariants.

Strict mode (raise on missing runtime) fires when either:
  - ``state.provider_selection.tts_provider_id == "piper"`` (explicit), OR
  - ``VOICE_TTS_STRICT=1`` env flag.

These tests pin every branch with mocked PiperProvider + runtime
shims; no real ``piper-tts`` install required.
"""
from __future__ import annotations

import io
import subprocess
import sys
import uuid
import wave
from pathlib import Path
from typing import Any

import pytest

from common.enums import ArtifactType, ProviderHealthStatus, StageName
from common.exceptions import StageRejection
from common.schemas import (
    AudioRef,
    DagState,
    ProviderHealth,
    StageOutput,
)


def _make_pcm_wav_bytes(
    duration_seconds: float = 0.4, sample_rate: int = 22050
) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        frames = int(sample_rate * duration_seconds)
        w.writeframes(b"\x00\x00" * frames)
    return buf.getvalue()


def _build_state(
    *,
    voice_mode: str = "tts",
    script_text: str | None = "Three calming bedtime habits.",
    tts_backend: str = "piper",
    provider_selection: dict[str, str | None] | None = None,
    audio_ref: AudioRef | None = None,
) -> DagState:
    return DagState(
        job_id=uuid.uuid4(),
        brief="phase 8g2 voice test",
        target_duration_seconds=30,
        synthetic_person_confirmed=True,
        consent_confirmed=True,
        watermark_required=True,
        c2pa_required=True,
        voice_mode=voice_mode,  # type: ignore[arg-type]
        script_text=script_text,
        tts_backend=tts_backend,
        audio_ref=audio_ref,
        provider_selection=provider_selection,
    )


# ---------------------------------------------------------------------------
# 1. Runtime-missing + explicit provider_selection → StageRejection
# ---------------------------------------------------------------------------


async def test_tts_runtime_missing_with_explicit_provider_raises(
    monkeypatch, tmp_path
):
    """provider_selection.tts_provider_id="piper" is the operator
    saying "I explicitly want Piper". Runtime missing → must raise,
    not silently fall back. Asserts: no fake narration, no noop success."""
    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path / "artifacts"))
    # Force the runtime probe to report missing regardless of host
    # state. We patch the provider module's symbol that the handler
    # imports lazily.
    import agents.voice.providers.piper.provider as piper_mod

    monkeypatch.setattr(piper_mod, "_piper_runtime_available", lambda: False)

    from agents.voice.handler import run as voice_run

    state = _build_state(
        provider_selection={"tts_provider_id": "piper"},
    )
    with pytest.raises(StageRejection) as exc:
        await voice_run(state)
    msg = str(exc.value)
    assert "tts_runtime_missing" in msg
    # Defensive: confirm no StageOutput leaked through.
    assert "noop=True" not in msg


# ---------------------------------------------------------------------------
# 2. Runtime present but assets missing → StageRejection(tts_assets_missing)
# ---------------------------------------------------------------------------


async def test_tts_assets_missing_with_explicit_provider_raises(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path / "artifacts"))
    import agents.voice.providers.piper.provider as piper_mod

    monkeypatch.setattr(piper_mod, "_piper_runtime_available", lambda: True)

    class _AssetsMissingPiper:
        _voice = "en_US-amy-medium"

        def healthcheck(self) -> ProviderHealth:
            return ProviderHealth(
                backend="piper",
                status=ProviderHealthStatus.missing_assets,
                missing_assets=[
                    "en_US-amy-medium.onnx",
                    "en_US-amy-medium.onnx.json",
                ],
                errors=["voices not found under PIPER_MODELS_ROOT"],
            )

        async def synthesize(self, req):  # pragma: no cover — unreachable
            raise RuntimeError("should not be called")

    monkeypatch.setattr(piper_mod, "PiperProvider", _AssetsMissingPiper)

    from agents.voice.handler import run as voice_run

    state = _build_state(provider_selection={"tts_provider_id": "piper"})
    with pytest.raises(StageRejection) as exc:
        await voice_run(state)
    assert "tts_assets_missing" in str(exc.value)


# ---------------------------------------------------------------------------
# 2b. healthcheck not_configured → tts_provider_not_configured
# ---------------------------------------------------------------------------


async def test_tts_provider_not_configured_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path / "artifacts"))
    import agents.voice.providers.piper.provider as piper_mod

    monkeypatch.setattr(piper_mod, "_piper_runtime_available", lambda: True)

    class _UnconfiguredPiper:
        _voice = "en_US-amy-medium"

        def healthcheck(self) -> ProviderHealth:
            return ProviderHealth(
                backend="piper",
                status=ProviderHealthStatus.not_configured,
                errors=["PIPER_MODELS_ROOT not set"],
            )

        async def synthesize(self, req):  # pragma: no cover
            raise RuntimeError("should not be called")

    monkeypatch.setattr(piper_mod, "PiperProvider", _UnconfiguredPiper)

    from agents.voice.handler import run as voice_run

    state = _build_state(provider_selection={"tts_provider_id": "piper"})
    with pytest.raises(StageRejection) as exc:
        await voice_run(state)
    assert "tts_provider_not_configured" in str(exc.value)


# ---------------------------------------------------------------------------
# 3. Mocked healthy Piper → real synthesis path → real ArtifactRef
# ---------------------------------------------------------------------------


async def test_tts_mocked_healthy_piper_emits_real_artifact_ref(
    monkeypatch, tmp_path
):
    """Pin the happy path with a fake-but-real PiperProvider: synthesize
    writes a tiny valid WAV; handler validates it via the Phase 3D
    inspector, emits a real ArtifactRef with checksum + dimensions."""
    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path / "artifacts"))
    import agents.voice.providers.piper.provider as piper_mod

    monkeypatch.setattr(piper_mod, "_piper_runtime_available", lambda: True)

    synthesize_called: dict[str, Any] = {"count": 0, "last_req": None}

    class _VoiceResultStub:
        def __init__(self, narration_uri: str, voice_id: str) -> None:
            self.narration_uri = narration_uri
            self.voice_id = voice_id
            self.model_version = "en_US-amy-medium.onnx"
            self.duration_ms = 400
            self.sample_rate = 22050
            self.phonemes_uri = None

    class _HealthyPiper:
        _voice = "en_US-amy-medium"

        def healthcheck(self) -> ProviderHealth:
            return ProviderHealth(
                backend="piper",
                status=ProviderHealthStatus.ok,
                models_root="/tmp/piper-mock",
            )

        async def synthesize(self, req):
            synthesize_called["count"] += 1
            synthesize_called["last_req"] = req
            # Write a tiny but valid PCM WAV to the requested path.
            out = Path(req.output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(_make_pcm_wav_bytes(duration_seconds=0.4))
            return _VoiceResultStub(out.as_uri(), self._voice)

    monkeypatch.setattr(piper_mod, "PiperProvider", _HealthyPiper)

    from agents.voice.handler import run as voice_run

    state = _build_state(provider_selection={"tts_provider_id": "piper"})
    output = await voice_run(state)

    # synthesize MUST have been called.
    assert synthesize_called["count"] == 1, (
        "real PiperProvider.synthesize must be called"
    )
    req = synthesize_called["last_req"]
    assert req is not None
    assert req.text == state.script_text
    assert req.voice_id == "en_US-amy-medium"
    # Stage output shape.
    assert isinstance(output, StageOutput)
    assert output.noop is False
    assert "narration" in output.artifacts
    narration = output.artifacts["narration"]
    assert narration.artifact_type == ArtifactType.audio.value
    assert narration.mime_type == "audio/wav"
    assert narration.checksum_sha256 is not None
    assert narration.size_bytes is not None and narration.size_bytes > 0
    assert narration.duration_seconds is not None and narration.duration_seconds > 0
    assert narration.sample_rate == 22050
    assert narration.channels == 1
    assert narration.local_path is not None
    assert Path(narration.local_path).is_file()
    # Phase 8G-2 metadata flags.
    assert narration.extra["real_tts"] is True
    assert narration.extra["provider_id"] == "piper"
    assert narration.extra["phase"] == "phase8g2_real_tts"


# ---------------------------------------------------------------------------
# 4. provider_selection is honored (explicit choice routes to Piper)
# ---------------------------------------------------------------------------


async def test_provider_selection_explicit_piper_routes_through(
    monkeypatch, tmp_path
):
    """Pin: provider_selection.tts_provider_id="piper" reaches PiperProvider
    even if state.tts_backend says something else."""
    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path / "artifacts"))
    import agents.voice.providers.piper.provider as piper_mod

    monkeypatch.setattr(piper_mod, "_piper_runtime_available", lambda: False)

    from agents.voice.handler import run as voice_run

    state = _build_state(
        tts_backend="something_else",  # would route elsewhere if respected
        provider_selection={"tts_provider_id": "piper"},
    )
    with pytest.raises(StageRejection) as exc:
        await voice_run(state)
    # The rejection comes from the Piper runtime-missing branch (proves
    # the handler reached Piper, not "something_else").
    assert "tts_runtime_missing" in str(exc.value)


# ---------------------------------------------------------------------------
# 5. Unknown provider → clean StageRejection, no fake artifact
# ---------------------------------------------------------------------------


async def test_unknown_provider_raises_no_fake_artifact(monkeypatch, tmp_path):
    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path / "artifacts"))
    from agents.voice.handler import run as voice_run

    state = _build_state(
        provider_selection={"tts_provider_id": "not_a_real_provider"},
    )
    with pytest.raises(StageRejection) as exc:
        await voice_run(state)
    msg = str(exc.value)
    assert "tts_provider_not_configured" in msg
    assert "not_a_real_provider" in msg


# ---------------------------------------------------------------------------
# 6. provided_audio regression — unchanged Phase 3D path
# ---------------------------------------------------------------------------


async def test_provided_audio_regression_still_works(monkeypatch, tmp_path):
    """The Phase 3D provided_audio path must keep working unchanged."""
    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("PROVIDED_AUDIO_ALLOWED_ROOTS", str(tmp_path))

    audio_path = tmp_path / "narration.wav"
    audio_path.write_bytes(_make_pcm_wav_bytes(duration_seconds=0.3))

    audio_ref = AudioRef(
        type="local_path",
        path=str(audio_path),
        mime_type="audio/wav",
        consent_confirmed=True,
        synthetic_or_owned_voice=True,
    )

    from agents.voice.handler import run as voice_run

    state = _build_state(
        voice_mode="provided_audio",
        script_text=None,
        audio_ref=audio_ref,
    )
    output = await voice_run(state)
    assert output.noop is False
    assert "narration" in output.artifacts
    narration = output.artifacts["narration"]
    assert narration.artifact_type == ArtifactType.audio.value
    assert narration.checksum_sha256 is not None
    assert narration.size_bytes is not None and narration.size_bytes > 0
    assert narration.duration_seconds is not None and narration.duration_seconds > 0
    assert narration.extra["source"] == "provided_audio"


# ---------------------------------------------------------------------------
# 7. Module-load isolation — no piper / torch / onnxruntime imported at load
# ---------------------------------------------------------------------------


def test_voice_handler_module_load_does_not_pull_heavy_deps():
    code = (
        "import sys\n"
        "import agents.voice.handler  # noqa: F401\n"
        "forbidden = ('piper','torch','onnxruntime','torchaudio')\n"
        "print(','.join(sorted(m for m in forbidden if m in sys.modules)))\n"
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
# 8. Legacy soft-fail — default state (no provider_selection, no Piper) →
# placeholder noop with categorised metadata. Pins the Phase 2/3 invariant.
# ---------------------------------------------------------------------------


async def test_default_state_runtime_missing_emits_categorised_placeholder(
    monkeypatch, tmp_path
):
    """Without explicit provider_selection and without VOICE_TTS_STRICT,
    a job that lands on the voice stage with no Piper installed gets a
    clearly-categorised placeholder, not a fake-success artifact."""
    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.delenv("VOICE_TTS_STRICT", raising=False)
    import agents.voice.providers.piper.provider as piper_mod

    monkeypatch.setattr(piper_mod, "_piper_runtime_available", lambda: False)

    from agents.voice.handler import run as voice_run

    state = _build_state()  # provider_selection=None, no strict env
    output = await voice_run(state)
    assert output.noop is True
    narration = output.artifacts["narration"]
    # Honest placeholder: NO checksum (so DagRunner won't promote to
    # the artifacts table) + explicit real_tts=False + categorised reason.
    assert narration.checksum_sha256 is None
    assert narration.extra["real_tts"] is False
    assert narration.extra["tts_skip_reason"] == "tts_runtime_missing"


# ---------------------------------------------------------------------------
# 9. VOICE_TTS_STRICT env flag makes the default state strict too
# ---------------------------------------------------------------------------


async def test_voice_tts_strict_env_makes_default_path_strict(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("VOICE_TTS_STRICT", "1")
    import agents.voice.providers.piper.provider as piper_mod

    monkeypatch.setattr(piper_mod, "_piper_runtime_available", lambda: False)

    from agents.voice.handler import run as voice_run

    state = _build_state()  # no explicit provider_selection
    with pytest.raises(StageRejection) as exc:
        await voice_run(state)
    assert "tts_runtime_missing" in str(exc.value)
