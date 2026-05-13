"""Voice — Phase 3C: voice-mode routing (still metadata-only).

Routes the DAG's voice stage by ``DagState.voice_mode``:

- ``"tts"`` (default) — keeps the Phase 2 no-op behavior: emits stub
  narration + phonemes artifact references. Wiring this branch to the
  real ``PiperProvider.synthesize()`` is a later phase; this preserves
  every existing Phase 1/2 test while the voice mode contract lands.
- ``"provided_audio"`` — new in Phase 3C. Validates the audio_ref's
  consent flags and (for ``local_path``) re-checks path safety as a
  defense-in-depth backstop to the API-layer schema validation. Emits an
  ``ArtifactRef`` whose ``uri`` points at the operator-supplied audio.
  No bytes are read; no transcoding is performed.

The handler never imports a TTS backend or reads the audio file. The
provider stubs in ``providers/`` (and the lazy-import Piper integration
shipped in Phase 3B) remain the only real-inference entry point and are
NOT wired into the DAG yet.
"""
from __future__ import annotations

from pathlib import Path

from common.enums import StageName
from common.exceptions import StageRejection
from common.schemas import ArtifactRef, AudioRef, DagState, StageOutput
from common.path_safety import validate_local_audio_path


def _stub_uri(job_id: str, filename: str) -> str:
    return f"s3://aivideo-jobs/{job_id}/{filename}"


def _audio_ref_to_uri(ref: AudioRef) -> str:
    """Render an AudioRef as a URI for downstream stages.

    Local paths become ``file://`` URIs; explicit artifact URIs are
    returned verbatim.
    """
    if ref.type == "local_path":
        return Path(ref.path).as_uri()
    return ref.path


# ---------------------------------------------------------------------------
# Mode handlers
# ---------------------------------------------------------------------------


def _run_tts_noop(state: DagState) -> StageOutput:
    """Phase 2 behavior preserved: emit stub narration + phonemes URIs.

    Phase 3C requires ``script_text`` on TTS mode (API schema enforces it;
    this is the defense-in-depth re-check at the handler boundary).
    """
    if not state.script_text or not state.script_text.strip():
        raise StageRejection(
            StageName.voice.value,
            "voice_mode='tts' requires non-empty script_text",
        )

    narration_ref = ArtifactRef(
        kind="audio",
        uri=_stub_uri(str(state.job_id), "narration.wav"),
        extra={
            "source": "tts",
            "tts_backend": state.tts_backend,
            "sample_rate": 48000,
            "channels": 1,
            "phase": "phase3c_tts_noop",
        },
    )
    phonemes_ref = ArtifactRef(
        kind="json",
        uri=_stub_uri(str(state.job_id), "phonemes.json"),
        extra={"source": "tts", "phase": "phase3c_tts_noop"},
    )
    return StageOutput(
        noop=True,
        notes=(
            f"voice no-op (tts via {state.tts_backend}): real TTS lives in "
            "agents/voice/providers/piper/provider.py and is not yet wired "
            "into the DAG handler."
        ),
        artifacts={"narration": narration_ref, "phonemes": phonemes_ref},
    )


def _run_provided_audio(state: DagState) -> StageOutput:
    """Phase 3C: validate metadata + path safety and emit an ArtifactRef.

    No bytes are read here. The handler just records what the operator
    declared (path, mime type, duration, checksum) and produces a
    reference that downstream stages can use exactly like a TTS-produced
    narration.
    """
    ref = state.audio_ref
    if ref is None:
        # Should be unreachable — API schema requires audio_ref for this
        # mode — but defense in depth.
        raise StageRejection(
            StageName.voice.value,
            "voice_mode='provided_audio' requires audio_ref (handler check)",
        )

    # Re-validate consent flags. They were validated at API time, but a
    # job could theoretically reach the handler via a non-API path in
    # future phases; the handler must not trust upstream alone.
    if not ref.consent_confirmed:
        raise StageRejection(
            StageName.voice.value,
            "audio_ref.consent_confirmed must be true",
        )
    if not ref.synthetic_or_owned_voice:
        raise StageRejection(
            StageName.voice.value,
            "audio_ref.synthetic_or_owned_voice must be true "
            "(voice cloning is not allowed)",
        )

    # Defense-in-depth path safety re-check.
    if ref.type == "local_path":
        try:
            validate_local_audio_path(ref.path)
        except ValueError as exc:
            raise StageRejection(StageName.voice.value, str(exc)) from exc

    narration_ref = ArtifactRef(
        kind="audio",
        uri=_audio_ref_to_uri(ref),
        sha256=ref.checksum,
        extra={
            "source": "provided_audio",
            "mime_type": ref.mime_type,
            "duration_seconds": ref.duration_seconds,
            "ref_type": ref.type,
            "phase": "phase3c",
        },
    )
    # No real phoneme extraction in Phase 3C (would require analyzing the
    # actual audio). Downstream stages get a stub phonemes URI; a future
    # phase can replace this with a real aligner-derived artifact.
    phonemes_ref = ArtifactRef(
        kind="json",
        uri=_stub_uri(str(state.job_id), "phonemes.json"),
        extra={"source": "provided_audio", "phase": "phase3c_stub"},
    )
    return StageOutput(
        noop=False,
        notes="voice mode='provided_audio': validated metadata, no transcoding",
        artifacts={"narration": narration_ref, "phonemes": phonemes_ref},
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run(state: DagState) -> StageOutput:
    mode = state.voice_mode
    if mode == "tts":
        return _run_tts_noop(state)
    if mode == "provided_audio":
        return _run_provided_audio(state)
    raise StageRejection(
        StageName.voice.value, f"unsupported voice_mode={mode!r}"
    )
