"""Voice provider registry. Same shape as the LipSync registry."""
from __future__ import annotations

from typing import TYPE_CHECKING

from common.exceptions import UnsupportedBackendError

if TYPE_CHECKING:
    from agents.voice.core.provider import VoiceProvider


def resolve(name: str) -> "VoiceProvider":
    n = (name or "").lower().strip()
    if n == "piper":
        from agents.voice.providers.piper.provider import PiperProvider

        return PiperProvider()
    raise UnsupportedBackendError(f"unknown TTS_BACKEND={name!r}")


def known_backends() -> list[str]:
    return ["piper"]
