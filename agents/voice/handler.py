"""Voice — Phase 3D: validate provided audio + populate full ArtifactRef metadata.

Routing (unchanged from Phase 3C):

- ``voice_mode="tts"`` — emits a stub ``narration.wav`` ``ArtifactRef``
  (no checksum, no real file). The DAG runner does NOT promote this to
  the ``artifacts`` table. Wiring the real Piper provider into the DAG
  remains a later phase.
- ``voice_mode="provided_audio"`` — validates the audio_ref's consent
  flags and path safety (defense-in-depth on top of the API schema), and
  for ``type="local_path"`` inspects the WAV file via
  ``common.audio_validation.validate_and_inspect_wav``. The resulting
  ``ArtifactRef`` carries ``checksum_sha256``, ``size_bytes``,
  ``duration_seconds``, ``sample_rate``, ``channels``, and
  ``local_path``. The DAG runner promotes any ``ArtifactRef`` with
  ``checksum_sha256`` set to the ``artifacts`` table.

Module-level imports stay light: ``wave`` + ``hashlib`` (via
``common.audio_validation``), no piper / torch / soundfile / numpy.
"""
from __future__ import annotations

import os
from pathlib import Path

from common.audio_validation import validate_and_inspect_wav
from common.enums import ArtifactType, StageName
from common.exceptions import StageRejection
from common.path_safety import validate_local_audio_path
from common.schemas import ArtifactRef, AudioRef, DagState, StageOutput


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


def _parse_int_csv(value: str) -> list[int] | None:
    """Parse a comma-separated env value into ints. Empty → None."""
    if not value:
        return None
    out: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if part:
            out.append(int(part))
    return out or None


# ---------------------------------------------------------------------------
# Mode handlers
# ---------------------------------------------------------------------------


def _run_tts_noop(state: DagState) -> StageOutput:
    """Phase 2/3C behavior preserved: emit stub narration + phonemes URIs."""
    if not state.script_text or not state.script_text.strip():
        raise StageRejection(
            StageName.voice.value,
            "voice_mode='tts' requires non-empty script_text",
        )

    narration_ref = ArtifactRef(
        artifact_type=ArtifactType.audio.value,
        uri=_stub_uri(str(state.job_id), "narration.wav"),
        extra={
            "source": "tts",
            "tts_backend": state.tts_backend,
            "sample_rate": 48000,
            "channels": 1,
            "phase": "phase3d_tts_noop",
        },
    )
    phonemes_ref = ArtifactRef(
        artifact_type=ArtifactType.metadata.value,
        uri=_stub_uri(str(state.job_id), "phonemes.json"),
        extra={"source": "tts", "phase": "phase3d_tts_noop"},
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
    """Validate audio_ref metadata + WAV header, emit fully-populated ref."""
    ref = state.audio_ref
    if ref is None:
        raise StageRejection(
            StageName.voice.value,
            "voice_mode='provided_audio' requires audio_ref (handler check)",
        )

    # Defense-in-depth consent re-check.
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

    # Path-safety re-check and (for local files) WAV header inspection.
    audio_meta = None
    local_path: str | None = None
    if ref.type == "local_path":
        try:
            validate_local_audio_path(ref.path)
        except ValueError as exc:
            raise StageRejection(StageName.voice.value, str(exc)) from exc

        max_size = _get_max_size_bytes()
        allowed_rates = _parse_int_csv(os.environ.get("AUDIO_ALLOWED_SAMPLE_RATES", ""))
        allowed_chans = _parse_int_csv(os.environ.get("AUDIO_ALLOWED_CHANNELS", ""))
        try:
            audio_meta = validate_and_inspect_wav(
                ref.path,
                mime_type=ref.mime_type,
                max_size_bytes=max_size,
                allowed_sample_rates=allowed_rates,
                allowed_channels=allowed_chans,
            )
        except ValueError as exc:
            raise StageRejection(StageName.voice.value, str(exc)) from exc
        local_path = str(audio_meta.path)

    narration_ref = ArtifactRef(
        artifact_type=ArtifactType.audio.value,
        uri=_audio_ref_to_uri(ref),
        local_path=local_path,
        # Prefer inspected metadata over operator-declared; fall back to
        # declared values if inspection didn't run (e.g. artifact_uri refs).
        checksum_sha256=(
            audio_meta.checksum_sha256 if audio_meta else ref.checksum
        ),
        size_bytes=audio_meta.size_bytes if audio_meta else None,
        duration_seconds=(
            audio_meta.duration_seconds if audio_meta else ref.duration_seconds
        ),
        sample_rate=audio_meta.sample_rate if audio_meta else None,
        channels=audio_meta.channels if audio_meta else None,
        extra={
            "source": "provided_audio",
            "mime_type": ref.mime_type,
            "ref_type": ref.type,
            "phase": "phase3d",
            "inspected": audio_meta is not None,
        },
    )
    # Phonemes remain a stub — alignment lands in a later phase.
    phonemes_ref = ArtifactRef(
        artifact_type=ArtifactType.metadata.value,
        uri=_stub_uri(str(state.job_id), "phonemes.json"),
        extra={"source": "provided_audio", "phase": "phase3d_stub"},
    )
    return StageOutput(
        noop=False,
        notes="voice mode='provided_audio': validated WAV header, no transcoding",
        artifacts={"narration": narration_ref, "phonemes": phonemes_ref},
    )


def _get_max_size_bytes() -> int | None:
    raw = os.environ.get("AUDIO_MAX_FILE_SIZE_BYTES")
    if not raw:
        return 52_428_800  # 50 MB default
    try:
        v = int(raw)
        return v if v > 0 else None
    except ValueError:
        return 52_428_800


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
