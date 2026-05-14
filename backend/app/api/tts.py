"""Phase 5A TTS generate endpoint.

Real Piper TTS generation when the runtime and voice assets are both
present. Otherwise returns a categorised 503 the frontend can pattern-
match on:

- ``tts_provider_not_configured`` — operator picked an unknown / disabled
  provider id, or the provider has no configuration at all.
- ``tts_runtime_missing`` — the provider is known but its Python runtime
  isn't importable (e.g. ``piper-tts`` not installed).
- ``tts_assets_missing`` — the runtime is present but voice files aren't
  on disk under ``PIPER_MODELS_ROOT``.

Generation path (only when runtime + assets are present):
1. Resolve the requested provider.
2. Generate a WAV under ``UPLOAD_AUDIO_ROOT`` with a uuid-derived name.
3. Validate the WAV via the existing Phase 3D inspector.
4. Register an ``ArtifactType.audio`` row with metadata + checksum.
5. Return the artifact metadata. No binary content in JSON.

NO voice cloning, NO model auto-download, NO external API.
"""
from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from common.audio_validation import validate_and_inspect_wav
from common.enums import ArtifactType

from app.core.config import settings
from app.core.deps import get_db_session
from app.services import artifact_service, upload_service

router = APIRouter(prefix="/api/v1/tts", tags=["tts"])


_ERROR_CODES = (
    "tts_provider_not_configured",
    "tts_provider_disabled",
    "tts_provider_not_implemented",
    "tts_runtime_missing",
    "tts_assets_missing",
    "tts_generation_failed",
)


class TTSGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    script_text: str = Field(..., min_length=1, max_length=8000)
    tts_provider_id: str = Field(default="piper", max_length=80)
    tts_model: str | None = Field(default=None, max_length=160)
    language: str | None = Field(default="en", max_length=16)
    output_format: Literal["wav"] = "wav"
    target_duration_seconds: int | None = None


class TTSGenerateError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal[
        "tts_provider_not_configured",
        "tts_provider_disabled",
        "tts_provider_not_implemented",
        "tts_runtime_missing",
        "tts_assets_missing",
        "tts_generation_failed",
    ]
    message: str
    provider_id: str


class TTSGenerateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["generated"]
    provider_id: str
    voice_id: str
    artifact_id: uuid.UUID
    uri: str
    mime_type: str
    checksum_sha256: str
    size_bytes: int
    duration_seconds: float
    sample_rate: int
    channels: int


def _raise_503(code: str, provider_id: str, message: str) -> None:
    err = TTSGenerateError(code=code, provider_id=provider_id, message=message)  # type: ignore[arg-type]
    raise HTTPException(status_code=503, detail=err.model_dump())


def _piper_runtime_available() -> bool:
    try:
        return importlib.util.find_spec("piper") is not None
    except Exception:
        return False


@router.post(
    "/generate",
    responses={503: {"model": TTSGenerateError}, 201: {"model": TTSGenerateResponse}},
    status_code=201,
)
async def tts_generate(
    payload: TTSGenerateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TTSGenerateResponse:
    provider_id = payload.tts_provider_id.strip() or "piper"

    if provider_id != "piper":
        # Only piper is wired for direct preview. Other providers reach
        # generation only through the future voice stage.
        _raise_503(
            "tts_provider_not_implemented",
            provider_id,
            f"TTS provider {provider_id!r} is not implemented for direct preview "
            "in this build.",
        )

    # Runtime check.
    if not _piper_runtime_available():
        _raise_503(
            "tts_runtime_missing",
            provider_id,
            "piper-tts runtime is not installed in this backend image. "
            "Install it (pip install piper-tts) and rebuild the backend.",
        )

    # Asset check via the existing Phase 3A/3B provider.
    from agents.voice.core.provider import VoiceRequest
    from agents.voice.providers.piper.provider import PiperProvider
    from common.enums import ProviderHealthStatus
    from common.exceptions import MissingAssetsError

    provider = PiperProvider()
    health = provider.healthcheck()
    if health.status is ProviderHealthStatus.not_configured:
        _raise_503(
            "tts_provider_not_configured",
            provider_id,
            "Piper provider is not configured. Set PIPER_MODELS_ROOT (or "
            "TTS_MODELS_ROOT) in the environment.",
        )
    if health.status is ProviderHealthStatus.missing_assets:
        missing_list = ", ".join(health.missing_assets or [])
        _raise_503(
            "tts_assets_missing",
            provider_id,
            "Piper voice assets are not present on disk: "
            f"{missing_list or '(none reported)'}. "
            "Place the .onnx + .onnx.json files manually under PIPER_MODELS_ROOT "
            "— no auto-download.",
        )
    if health.status is not ProviderHealthStatus.ok:
        _raise_503(
            "tts_provider_not_configured",
            provider_id,
            f"Piper provider is in state {health.status.value!r}. See backend logs.",
        )

    # ----- Real generation path -----
    root = upload_service.get_upload_root("UPLOAD_AUDIO_ROOT", settings.upload_audio_root)
    out_name = upload_service.safe_unique_filename(".wav")
    dest = root / out_name
    voice_id = payload.tts_model or provider._voice  # type: ignore[attr-defined]

    try:
        result = await provider.synthesize(
            VoiceRequest(
                voice_id=voice_id,
                text=payload.script_text,
                output_path=dest,
            )
        )
    except MissingAssetsError as exc:
        _raise_503("tts_assets_missing", provider_id, str(exc))
    except Exception as exc:  # pragma: no cover — defensive
        # If anything blows up inside the runtime, scrub the partial file and
        # surface a clean 503.
        try:
            dest.unlink(missing_ok=True)
        except Exception:
            pass
        _raise_503(
            "tts_generation_failed",
            provider_id,
            f"piper synthesis failed: {type(exc).__name__}: {exc}",
        )

    # Validate the WAV via the existing Phase 3D inspector — confirms it's
    # a real PCM WAV with the metadata we expect, and gives us the
    # checksum + duration in one pass.
    max_size = settings.audio_max_file_size_bytes
    try:
        meta = validate_and_inspect_wav(
            Path(result.output_path), mime_type="audio/wav", max_size_bytes=max_size
        )
    except ValueError as exc:
        try:
            Path(result.output_path).unlink(missing_ok=True)
        except Exception:
            pass
        _raise_503(
            "tts_generation_failed",
            provider_id,
            f"piper produced a WAV that failed validation: {exc}",
        )

    metadata_json = {
        "phase": "phase5a_tts_generate",
        "source": "tts_generate",
        "provider_id": provider_id,
        "voice_id": voice_id,
        "language": payload.language,
        "sample_rate": meta.sample_rate,
        "channels": meta.channels,
        "duration_seconds": meta.duration_seconds,
        "mime_type": "audio/wav",
    }
    artifact = await artifact_service.register_artifact(
        session,
        artifact_type=ArtifactType.audio.value,
        uri=Path(result.output_path).as_uri(),
        local_path=str(result.output_path),
        mime_type="audio/wav",
        checksum_sha256=meta.checksum_sha256,
        size_bytes=meta.size_bytes,
        duration_seconds=meta.duration_seconds,
        sample_rate=meta.sample_rate,
        channels=meta.channels,
        metadata_json=metadata_json,
    )
    return TTSGenerateResponse(
        status="generated",
        provider_id=provider_id,
        voice_id=voice_id,
        artifact_id=artifact.id,
        uri=artifact.uri,
        mime_type="audio/wav",
        checksum_sha256=meta.checksum_sha256,
        size_bytes=meta.size_bytes,
        duration_seconds=meta.duration_seconds,
        sample_rate=meta.sample_rate,
        channels=meta.channels,
    )


# Re-export ``_ERROR_CODES`` for tests + frontend type generation hints.
__all__ = [
    "TTSGenerateRequest",
    "TTSGenerateResponse",
    "TTSGenerateError",
    "router",
    "_ERROR_CODES",
]


# Silence the "unused" linter — codes are documented for downstream parsing.
_ = _ERROR_CODES
# Avoid an unused-import warning when ``os`` is needed only inside a
# future branch.
_ = os
