"""Piper provider — Phase 3B (narrow) integration path.

What's real here:
- ``synthesize()`` actually runs Piper to produce a WAV file on disk —
  **if and only if** (a) the ``piper`` Python package is installed, and
  (b) the required voice model files are present at the configured root.
- If either is missing, ``synthesize()`` fails fast with a clear,
  actionable error and never reaches a Piper API call.

What's explicitly NOT done:
- The ``piper`` package is **not** declared as a hard dependency in any
  pyproject.toml. Operators opt in by ``pip install piper-tts`` separately.
- No model weights are downloaded. Operators place the ``.onnx`` +
  ``.onnx.json`` files under ``$PIPER_MODELS_ROOT`` manually.
- The DAG handler in ``agents/voice/handler.py`` is still the Phase 2
  no-op. Wiring the provider into the DAG is a later phase.

Module-level imports stay light: we only import ``piper`` lazily inside
``synthesize()`` so test environments (and any deployment that doesn't
need TTS) load this file cleanly even if Piper isn't installed.
"""
from __future__ import annotations

import importlib.util
import os
import tempfile
import wave
from pathlib import Path
from typing import ClassVar

from common.enums import ProviderHealthStatus
from common.exceptions import MissingAssetsError, ProviderNotImplementedError
from common.schemas import AssetSpec, ProviderHealth

from agents.voice.core.provider import VoiceProvider, VoiceRequest, VoiceResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_models_root() -> Path | None:
    """PIPER_MODELS_ROOT wins; otherwise TTS_MODELS_ROOT/piper."""
    explicit = os.environ.get("PIPER_MODELS_ROOT")
    if explicit:
        return Path(explicit)
    tts_root = os.environ.get("TTS_MODELS_ROOT")
    if tts_root:
        return Path(tts_root) / "piper"
    return None


def _resolve_default_voice() -> str:
    return os.environ.get("TTS_DEFAULT_VOICE", "en_US-amy-medium")


def _piper_runtime_available() -> bool:
    """Cheap check: is the ``piper`` package importable? Uses
    ``importlib.util.find_spec`` so we don't actually import it here."""
    return importlib.util.find_spec("piper") is not None


def _lazy_import_piper_voice():
    """Lazy import of ``PiperVoice``.

    Different Piper versions expose the class at slightly different
    paths. We try the most common one first, fall back to the older
    location, and surface a ``ProviderNotImplementedError`` if neither is
    importable.
    """
    try:
        # Piper 1.x canonical location.
        from piper.voice import PiperVoice  # type: ignore[import-not-found]

        return PiperVoice
    except ImportError:
        pass
    try:
        # Older Piper / alternative packaging.
        from piper import PiperVoice  # type: ignore[import-not-found]

        return PiperVoice
    except ImportError as exc:
        raise ProviderNotImplementedError(
            "piper Python package not installed; install with "
            "`pip install piper-tts` to enable Phase 3B real TTS. "
            f"(import error: {exc})"
        ) from exc


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class PiperProvider(VoiceProvider):
    name: ClassVar[str] = "piper"

    def __init__(
        self,
        *,
        models_root: Path | None = None,
        default_voice: str | None = None,
    ) -> None:
        self._models_root = (
            models_root if models_root is not None else _resolve_models_root()
        )
        self._voice = default_voice or _resolve_default_voice()

    # ------------------------------------------------------------- contract

    def required_assets(self) -> list[AssetSpec]:
        return [
            AssetSpec(
                relative_path=f"{self._voice}.onnx",
                description=f"Piper voice model: {self._voice} (ONNX)",
                license_note="Per-voice license — see Piper voice card",
            ),
            AssetSpec(
                relative_path=f"{self._voice}.onnx.json",
                description=f"Piper voice config: {self._voice}",
                license_note="Per-voice license",
            ),
        ]

    def healthcheck(self) -> ProviderHealth:
        # Always include runtime-availability info in `extra` so operators
        # running an interactive healthcheck see both at a glance.
        extra: dict = {
            "voice": self._voice,
            "piper_runtime_installed": _piper_runtime_available(),
        }

        if self._models_root is None:
            return ProviderHealth(
                backend=self.name,
                status=ProviderHealthStatus.not_configured,
                errors=[
                    "Neither PIPER_MODELS_ROOT nor TTS_MODELS_ROOT is set. "
                    "Set one in .env."
                ],
                extra=extra,
            )
        if not self._models_root.exists():
            return ProviderHealth(
                backend=self.name,
                status=ProviderHealthStatus.missing_assets,
                models_root=str(self._models_root),
                missing_assets=[a.relative_path for a in self.required_assets()],
                errors=[f"models_root does not exist on disk: {self._models_root}"],
                extra=extra,
            )
        missing = [
            a.relative_path
            for a in self.required_assets()
            if not (self._models_root / a.relative_path).is_file()
        ]
        if missing:
            return ProviderHealth(
                backend=self.name,
                status=ProviderHealthStatus.missing_assets,
                models_root=str(self._models_root),
                missing_assets=missing,
                errors=[
                    f"{len(missing)} required Piper file(s) missing under "
                    f"{self._models_root} for voice {self._voice!r}; "
                    "place them manually (no auto-download)."
                ],
                extra=extra,
            )
        return ProviderHealth(
            backend=self.name,
            status=ProviderHealthStatus.ok,
            models_root=str(self._models_root),
            extra=extra,
        )

    # ------------------------------------------------------------ synthesize

    async def synthesize(self, req: VoiceRequest) -> VoiceResult:
        """Phase 3B narrow — Piper-only.

        Order:
          1. Assets check (file existence).
          2. Lazy import the Piper runtime — refuse cleanly if not installed.
          3. Load the voice and write a WAV.

        Auto-download is OFF by design (and intentionally not honored even
        when ``ALLOW_MODEL_AUTODOWNLOAD=true`` — that flag is reserved for
        a future, explicit fetch helper, not for silent at-runtime pulls).
        """
        # 1. Assets must exist on disk.
        health = self.healthcheck()
        if health.status is not ProviderHealthStatus.ok:
            raise MissingAssetsError(self.name, health.missing_assets)

        # 2. Lazy-import; raises ProviderNotImplementedError if piper absent.
        PiperVoice = _lazy_import_piper_voice()  # noqa: N806

        # 3. Resolve paths and an output destination.
        assert self._models_root is not None  # healthcheck guarantees this
        model_path = self._models_root / f"{self._voice}.onnx"
        config_path = self._models_root / f"{self._voice}.onnx.json"

        if req.output_path:
            output_path = Path(req.output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            # Caller didn't choose a path — write to a tempfile so the
            # call still works in ad-hoc scripts. Caller can promote the
            # file to MinIO afterwards.
            fd, tmp_name = tempfile.mkstemp(
                prefix=f"aivideo-piper-{req.job_id}-",
                suffix=".wav",
            )
            os.close(fd)
            output_path = Path(tmp_name)

        # 4. Real Piper synthesis. The Piper API takes a wave.Wave_write
        # and writes audio frames into it. `wave` is stdlib.
        # NOTE: PiperVoice.load() signatures differ slightly between
        # versions — recent versions look for the JSON config next to
        # the .onnx automatically; we pass it explicitly to be robust.
        try:
            voice = PiperVoice.load(str(model_path), config_path=str(config_path))
        except TypeError:
            # Older Piper signature didn't accept a kwarg.
            voice = PiperVoice.load(str(model_path))

        with wave.open(str(output_path), "wb") as wav_file:
            voice.synthesize(req.text, wav_file)

        with wave.open(str(output_path), "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            n_frames = wav_file.getnframes()
            duration_ms = int(round(n_frames / sample_rate * 1000)) if sample_rate else 0

        return VoiceResult(
            narration_uri=output_path.as_uri(),
            phonemes_uri=None,
            duration_ms=duration_ms,
            sample_rate=sample_rate,
            model_version=model_path.name,
            voice_id=self._voice,
        )
