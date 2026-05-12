"""Piper provider — Phase 3A stub.

Implements ``VoiceProvider``:
- declares the ``.onnx`` + ``.json`` voice files Piper needs (per the
  ``TTS_DEFAULT_VOICE`` configured in ``.env``);
- resolves ``models_root`` from ``PIPER_MODELS_ROOT`` (preferred) or
  ``TTS_MODELS_ROOT/piper``;
- on-disk healthcheck;
- raises ``ProviderNotImplementedError`` from ``synthesize()``.

Does NOT import ``piper`` (the runtime package) or any model framework.
Real TTS lands in Phase 3B.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar

from common.enums import ProviderHealthStatus
from common.exceptions import MissingAssetsError, ProviderNotImplementedError
from common.schemas import AssetSpec, ProviderHealth

from agents.voice.core.provider import VoiceProvider, VoiceRequest, VoiceResult


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
    """The voice id to require at healthcheck time."""
    return os.environ.get("TTS_DEFAULT_VOICE", "en_US-amy-medium")


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
        """Piper packages each voice as a paired ``.onnx`` + ``.onnx.json``.

        The Phase 3A check just looks for the configured default voice;
        Phase 3B will expand this to whatever set of voices is declared in
        ``configs/voices/`` so a multi-voice deployment can be validated
        in one healthcheck.
        """
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
        if self._models_root is None:
            return ProviderHealth(
                backend=self.name,
                status=ProviderHealthStatus.not_configured,
                errors=[
                    "Neither PIPER_MODELS_ROOT nor TTS_MODELS_ROOT is set. "
                    "Set one in .env."
                ],
                extra={"voice": self._voice},
            )
        if not self._models_root.exists():
            return ProviderHealth(
                backend=self.name,
                status=ProviderHealthStatus.missing_assets,
                models_root=str(self._models_root),
                missing_assets=[a.relative_path for a in self.required_assets()],
                errors=[f"models_root does not exist on disk: {self._models_root}"],
                extra={"voice": self._voice},
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
                extra={"voice": self._voice},
            )
        return ProviderHealth(
            backend=self.name,
            status=ProviderHealthStatus.ok,
            models_root=str(self._models_root),
            extra={"voice": self._voice, "phase": "3a_stub", "real_inference": False},
        )

    async def synthesize(self, req: VoiceRequest) -> VoiceResult:
        """Phase 3A fail-fast synthesize.

        Order: assets first (no compliance token gates the voice stage).
        Always raises in Phase 3A — real Piper inference is deferred.
        """
        health = self.healthcheck()
        if health.status is not ProviderHealthStatus.ok:
            raise MissingAssetsError(self.name, health.missing_assets)

        raise ProviderNotImplementedError(
            "piper: real TTS lands in Phase 3B; "
            "Phase 3A only validates the contract + assets."
        )
