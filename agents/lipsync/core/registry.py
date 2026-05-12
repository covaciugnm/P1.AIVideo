"""LipSync provider registry.

Maps a backend name (``LIPSYNC_BACKEND``) to its concrete provider class.
The orchestrator looks up providers through ``resolve()`` and never
imports concrete classes directly.

Providers are imported lazily inside ``resolve()`` so a placeholder
provider (MuseTalk / Wav2Lip) that doesn't yet have full deps installed
doesn't crash an agent at startup just because a different backend is
selected.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from common.exceptions import UnsupportedBackendError

if TYPE_CHECKING:
    from agents.lipsync.core.provider import LipSyncProvider


def resolve(name: str) -> "LipSyncProvider":
    """Return a fresh provider instance for the given backend name."""
    n = (name or "").lower().strip()
    if n == "sadtalker":
        from agents.lipsync.providers.sadtalker.provider import SadTalkerProvider

        return SadTalkerProvider()
    if n == "musetalk":
        from agents.lipsync.providers.musetalk.provider import MuseTalkProvider

        return MuseTalkProvider()
    if n == "wav2lip":
        from agents.lipsync.providers.wav2lip.provider import Wav2LipProvider

        return Wav2LipProvider()
    raise UnsupportedBackendError(f"unknown LIPSYNC_BACKEND={name!r}")


def known_backends() -> list[str]:
    """Names that ``resolve()`` knows about. Useful for healthcheck UIs."""
    return ["sadtalker", "musetalk", "wav2lip"]
