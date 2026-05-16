"""Voice DAG stage — Phase 8G-2: real Piper TTS via PiperProvider.

Routing:

- ``voice_mode="provided_audio"`` — unchanged Phase 3D path: validate
  the operator-supplied ``audio_ref``, inspect the WAV header, emit a
  fully-populated ``ArtifactRef`` (the DAG runner promotes refs with
  ``checksum_sha256`` set to the ``artifacts`` table). No TTS work.

- ``voice_mode="tts"`` — Phase 8G-2 makes this real. We resolve the
  TTS provider in this order:
  1. ``state.provider_selection.tts_provider_id`` (operator explicit choice)
  2. ``state.tts_backend`` (job default)
  3. ``"piper"`` (project default)

  For ``piper``:
  - Probe the runtime (``importlib.util.find_spec("piper")``).
  - If the runtime is missing **and** the operator explicitly selected
    Piper via ``provider_selection`` **or** ``VOICE_TTS_STRICT=1`` is
    set → raise ``StageRejection("tts_runtime_missing: ...")``.
  - If the runtime is missing in the default case (no explicit choice,
    no strict flag — e.g. Phase 2/3 metadata-only DAG runs in the
    light backend image) → emit a clearly-categorised placeholder
    ``StageOutput(noop=True)`` with ``extra.real_tts=False`` and
    ``extra.tts_skip_reason="tts_runtime_missing"`` so downstream
    stages can decide whether to short-circuit. **This is not a fake
    success** — the placeholder advertises that real TTS was not run.
  - If the runtime is present → call ``PiperProvider().healthcheck()``.
    ``not_configured`` / ``missing_assets`` / other non-``ok`` →
    ``StageRejection`` with the matching category. The contract is
    that a configured-but-broken provider must fail loudly.
  - If healthcheck is ``ok`` → run real ``synthesize()``, validate the
    WAV via the Phase 3D inspector, emit a real ``ArtifactRef`` with
    ``noop=False`` carrying checksum / size / duration / sample_rate /
    channels. The DAG runner promotes it to the ``artifacts`` table.

Non-``piper`` providers raise ``StageRejection("tts_provider_not_configured: ...")``
— only Piper is wired in this DAG path. Other TTS providers stay
catalog-only (Phase 6D).

Module-level imports stay light: no ``piper``, no ``torch``, no
``onnxruntime`` at load time. The provider import is lazy inside
``_run_tts``.
"""
from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

from common.audio_validation import validate_and_inspect_wav
from common.enums import ArtifactType, ProviderHealthStatus, StageName
from common.exceptions import (
    MissingAssetsError,
    ProviderNotImplementedError,
    StageRejection,
)
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


def _get_max_size_bytes() -> int | None:
    raw = os.environ.get("AUDIO_MAX_FILE_SIZE_BYTES")
    if not raw:
        return 52_428_800  # 50 MB default
    try:
        v = int(raw)
        return v if v > 0 else None
    except ValueError:
        return 52_428_800


def _strict_tts_mode(state: DagState) -> bool:
    """Strict mode triggers a hard StageRejection on missing runtime.

    Strict when either:
    - the operator explicitly chose a TTS provider via
      ``provider_selection.tts_provider_id`` (any non-empty value);
    - ``VOICE_TTS_STRICT`` env is set to a truthy string.
    """
    if state.provider_selection:
        sel = state.provider_selection.get("tts_provider_id")
        if isinstance(sel, str) and sel.strip():
            return True
    return os.environ.get("VOICE_TTS_STRICT", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _resolve_tts_provider_id(state: DagState) -> str:
    """Resolve which TTS provider the operator wants.

    Priority (explicit → default):
    1. ``state.provider_selection["tts_provider_id"]``
    2. ``state.tts_backend``
    3. ``"piper"``
    """
    if state.provider_selection:
        sel = state.provider_selection.get("tts_provider_id")
        if isinstance(sel, str) and sel.strip():
            return sel.strip()
    if state.tts_backend and state.tts_backend.strip():
        return state.tts_backend.strip()
    return "piper"


def _soft_noop_narration(
    state: DagState, *, reason: str, note: str
) -> StageOutput:
    """Phase 8G-2 — categorised placeholder when the operator-default
    Piper runtime is absent but no explicit opt-in / strict flag is set.

    This is **not** a fake success. The returned narration_ref carries
    ``extra.real_tts=False`` and ``extra.tts_skip_reason=<category>``
    so downstream stages can see exactly what happened. The DAG runner
    does NOT promote this to the artifacts table (no checksum_sha256).

    Path preserved primarily for Phase 2/3 metadata-only end-to-end
    tests against the default light backend (no Piper installed).
    """
    narration_ref = ArtifactRef(
        artifact_type=ArtifactType.audio.value,
        uri=_stub_uri(str(state.job_id), "narration.wav"),
        extra={
            "source": "tts",
            "tts_backend": state.tts_backend,
            "real_tts": False,
            "tts_skip_reason": reason,
            "phase": "phase8g2_runtime_missing_placeholder",
        },
    )
    phonemes_ref = ArtifactRef(
        artifact_type=ArtifactType.metadata.value,
        uri=_stub_uri(str(state.job_id), "phonemes.json"),
        extra={
            "source": "tts",
            "real_tts": False,
            "phase": "phase8g2_runtime_missing_placeholder",
        },
    )
    return StageOutput(
        noop=True,
        notes=f"voice tts placeholder ({reason}): {note}",
        artifacts={"narration": narration_ref, "phonemes": phonemes_ref},
    )


def _safe_cleanup(p: Path) -> None:
    try:
        p.unlink(missing_ok=True)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Mode handlers
# ---------------------------------------------------------------------------


async def _run_tts(state: DagState) -> StageOutput:
    """Phase 8G-2 real-Piper TTS routing."""
    if not state.script_text or not state.script_text.strip():
        raise StageRejection(
            StageName.voice.value,
            "voice_mode='tts' requires non-empty script_text",
        )

    provider_id = _resolve_tts_provider_id(state)
    if provider_id != "piper":
        # Phase 6D catalog has many TTS entries, but only Piper is
        # wired into the DAG. Other providers (xtts, coqui, external
        # APIs) stay catalog-only until they ship their own adapters.
        raise StageRejection(
            StageName.voice.value,
            (
                f"tts_provider_not_configured: only 'piper' is wired in this "
                f"DAG; selected provider {provider_id!r} has no DAG adapter."
            ),
        )

    # Lazy import — keeps ``agents.voice.handler`` module-load light.
    from agents.voice.providers.piper.provider import (
        PiperProvider,
        _piper_runtime_available,
    )
    from agents.voice.core.provider import VoiceRequest

    strict = _strict_tts_mode(state)
    runtime_ok = _piper_runtime_available()

    if not runtime_ok:
        if strict:
            raise StageRejection(
                StageName.voice.value,
                "tts_runtime_missing: piper-tts is not installed in this "
                "image. Rebuild with --build-arg INSTALL_PIPER=true or "
                "pip install backend[tts] (see docs/runbooks/piper-runtime.md).",
            )
        return _soft_noop_narration(
            state,
            reason="tts_runtime_missing",
            note=(
                "piper-tts not installed in this image; emitting placeholder "
                "narration_ref. Real TTS requires INSTALL_PIPER=true or "
                "explicit provider_selection.tts_provider_id='piper'."
            ),
        )

    provider = PiperProvider()
    try:
        health = provider.healthcheck()
    except Exception as exc:  # defensive
        raise StageRejection(
            StageName.voice.value,
            f"tts_provider_not_configured: piper healthcheck raised "
            f"{type(exc).__name__}: {exc}",
        ) from exc

    status_value = getattr(health.status, "value", str(health.status))
    if status_value == "not_configured":
        raise StageRejection(
            StageName.voice.value,
            f"tts_provider_not_configured: "
            f"{health.errors[0] if health.errors else 'PIPER_MODELS_ROOT not set'}",
        )
    if status_value == "missing_assets":
        raise StageRejection(
            StageName.voice.value,
            f"tts_assets_missing: "
            f"{health.errors[0] if health.errors else 'piper voice files not on disk'}",
        )
    if status_value == "not_implemented":
        raise StageRejection(
            StageName.voice.value,
            f"tts_provider_not_implemented: "
            f"{health.errors[0] if health.errors else 'piper reports not_implemented'}",
        )
    if status_value != "ok":
        raise StageRejection(
            StageName.voice.value,
            f"tts_provider_not_configured: piper status={status_value!r}",
        )

    # Real synthesis.
    base_root = (
        os.environ.get("ARTIFACTS_LOCAL_ROOT") or tempfile.gettempdir()
    )
    out_dir = Path(base_root) / "audio" / str(state.job_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"narration_{uuid.uuid4().hex}.wav"

    req = VoiceRequest(
        job_id=state.job_id,
        voice_id=getattr(provider, "_voice", "en_US-amy-medium"),
        text=state.script_text,
        output_path=str(output_path),
    )

    try:
        result = await provider.synthesize(req)
    except MissingAssetsError as exc:
        _safe_cleanup(output_path)
        raise StageRejection(
            StageName.voice.value, f"tts_assets_missing: {exc}"
        ) from exc
    except ProviderNotImplementedError as exc:
        _safe_cleanup(output_path)
        raise StageRejection(
            StageName.voice.value, f"tts_runtime_missing: {exc}"
        ) from exc
    except Exception as exc:
        _safe_cleanup(output_path)
        raise StageRejection(
            StageName.voice.value,
            f"tts_generation_failed: {type(exc).__name__}: {exc}",
        ) from exc

    # Inspect the WAV. The result.output_path may differ from output_path
    # if the provider chose its own tempfile (only when output_path=None,
    # which isn't our case — but be defensive).
    actual_path = Path(result.narration_uri.replace("file://", "")) if result.narration_uri.startswith("file://") else output_path
    if not actual_path.is_file():
        # Fallback to the path we requested.
        actual_path = output_path
    if not actual_path.is_file():
        raise StageRejection(
            StageName.voice.value,
            "tts_generation_failed: synthesize returned but no WAV on disk",
        )

    try:
        audio_meta = validate_and_inspect_wav(
            str(actual_path),
            mime_type="audio/wav",
            max_size_bytes=_get_max_size_bytes(),
        )
    except ValueError as exc:
        _safe_cleanup(actual_path)
        raise StageRejection(
            StageName.voice.value,
            f"tts_generation_failed: generated WAV failed validation: {exc}",
        ) from exc

    narration_ref = ArtifactRef(
        artifact_type=ArtifactType.audio.value,
        uri=actual_path.as_uri(),
        local_path=str(actual_path),
        mime_type="audio/wav",
        checksum_sha256=audio_meta.checksum_sha256,
        size_bytes=audio_meta.size_bytes,
        duration_seconds=audio_meta.duration_seconds,
        sample_rate=audio_meta.sample_rate,
        channels=audio_meta.channels,
        extra={
            "source": "tts",
            "provider_id": "piper",
            "real_tts": True,
            "voice_id": result.voice_id,
            "model_version": result.model_version,
            "phase": "phase8g2_real_tts",
        },
    )
    # Phonemes remain a metadata stub; alignment lands in a later phase.
    phonemes_ref = ArtifactRef(
        artifact_type=ArtifactType.metadata.value,
        uri=_stub_uri(str(state.job_id), "phonemes.json"),
        extra={
            "source": "tts",
            "real_tts": True,
            "phase": "phase8g2_real_tts",
        },
    )
    return StageOutput(
        noop=False,
        notes=(
            f"voice tts via piper: synthesised {audio_meta.size_bytes} bytes "
            f"at {actual_path}"
        ),
        artifacts={"narration": narration_ref, "phonemes": phonemes_ref},
    )


def _run_provided_audio(state: DagState) -> StageOutput:
    """Validate audio_ref metadata + WAV header, emit fully-populated ref.

    Unchanged from Phase 3D. Provided-audio mode never hits Piper.
    """
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


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run(state: DagState) -> StageOutput:
    mode = state.voice_mode
    if mode == "tts":
        return await _run_tts(state)
    if mode == "provided_audio":
        return _run_provided_audio(state)
    raise StageRejection(
        StageName.voice.value, f"unsupported voice_mode={mode!r}"
    )
