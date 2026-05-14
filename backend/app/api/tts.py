"""Phase 4F TTS generate endpoint.

In the light runtime no TTS runtime is wired (Phase 3B's Piper provider
stays off until piper-tts is installed + a voice file is placed). So this
endpoint refuses with a clean 503 carrying a machine-readable code the
frontend can pattern-match on.

Real TTS generation lands when a provider's ``synthesize()`` is wired
into the DAG. Phase 4F deliberately does not call any real provider here
to keep the boundary clean — the operator triggers generation through
the job pipeline once a real provider is configured.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/api/v1/tts", tags=["tts"])


class TTSGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    script_text: str = Field(..., min_length=1, max_length=8000)
    tts_provider_id: str = Field(default="piper", max_length=80)
    tts_model: str | None = Field(default=None, max_length=160)
    language: str | None = Field(default="en", max_length=16)
    output_format: Literal["wav", "mp3"] = "wav"
    target_duration_seconds: int | None = None


class TTSGenerateError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal[
        "tts_provider_not_configured",
        "tts_provider_disabled",
        "tts_provider_not_implemented",
    ]
    message: str
    provider_id: str


@router.post("/generate", responses={503: {"model": TTSGenerateError}})
async def tts_generate(payload: TTSGenerateRequest) -> None:
    # No real provider is implemented in light mode. The orchestrator's
    # voice stage owns real synthesis; this endpoint is the operator-
    # facing "preview" hook and stays a clean 503 until a runtime is
    # wired.
    err = TTSGenerateError(
        code="tts_provider_not_configured",
        provider_id=payload.tts_provider_id,
        message=(
            "TTS provider is not configured for direct preview. Install "
            "the provider's runtime (e.g. piper-tts) and place voice "
            "assets, then enable the provider in Settings."
        ),
    )
    raise HTTPException(status_code=503, detail=err.model_dump())
