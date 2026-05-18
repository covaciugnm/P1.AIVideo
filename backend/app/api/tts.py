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
import logging
import os
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

logger = logging.getLogger(__name__)
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
    logger.info(
        "tts.generate.start provider=%s lang=%s script_chars=%d",
        provider_id, payload.language, len(payload.script_text or ""),
        extra={"provider_id": provider_id, "phase": "tts.generate.start"},
    )

    # Phase 10A-1 — route F5TTS-Ro to the optional HTTP wrapper service.
    if provider_id == "f5tts_ro":
        return await _generate_via_f5tts_ro(payload, session)

    if provider_id != "piper":
        # Only piper + f5tts_ro are wired for direct preview. Other
        # providers reach generation only through the future voice stage.
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

    # Phase 8G fix — VoiceRequest requires ``job_id`` and accepts
    # ``output_path`` as a ``str``. The /api/v1/tts/generate preview
    # is unattached to a real job (Phase 5A "preview-only" pattern),
    # so we mint a synthetic UUID for traceability.
    try:
        result = await provider.synthesize(
            VoiceRequest(
                job_id=uuid.uuid4(),
                voice_id=voice_id,
                text=payload.script_text,
                output_path=str(dest),
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
            Path(dest), mime_type="audio/wav", max_size_bytes=max_size
        )
    except ValueError as exc:
        try:
            Path(dest).unlink(missing_ok=True)
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
        uri=Path(dest).as_uri(),
        local_path=str(dest),
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


def _chunk_script_for_tts(text: str, max_chars: int = 180) -> list[str]:
    """Phase 12Y — split a long script into TTS-batch-sized chunks.

    F5TTS-Ro generates audio in a single forward pass of bounded length;
    scripts that would produce more than ~15 s of speech get truncated.
    This splitter cuts on sentence boundaries (``.``, ``!``, ``?``,
    ``…``, ``:`` ) first, falls back to commas / semicolons for very
    long single sentences, and finally hard-wraps at ``max_chars``
    when no punctuation is present.

    Returns one or more chunk strings whose concatenation equals the
    original (modulo whitespace folding).
    """
    import re

    if not text or not text.strip():
        return [text]
    # Normalise whitespace.
    text = re.sub(r"\s+", " ", text.strip())

    # Split on strong punctuation, keeping the delimiter on the
    # left-hand side so the chunk reads naturally.
    pieces = re.split(r"(?<=[.!?…])\s+", text)
    chunks: list[str] = []
    buf = ""
    for p in pieces:
        candidate = (buf + " " + p).strip() if buf else p
        if len(candidate) <= max_chars:
            buf = candidate
            continue
        if buf:
            chunks.append(buf)
            buf = ""
        # ``p`` alone exceeds ``max_chars`` — split on commas / semicolons.
        if len(p) > max_chars:
            sub_pieces = re.split(r"(?<=[,;:])\s+", p)
            sub_buf = ""
            for sp in sub_pieces:
                sub_candidate = (sub_buf + " " + sp).strip() if sub_buf else sp
                if len(sub_candidate) <= max_chars:
                    sub_buf = sub_candidate
                    continue
                if sub_buf:
                    chunks.append(sub_buf)
                    sub_buf = ""
                if len(sp) > max_chars:
                    # Hard wrap — last resort.
                    for i in range(0, len(sp), max_chars):
                        chunks.append(sp[i : i + max_chars].strip())
                else:
                    sub_buf = sp
            if sub_buf:
                chunks.append(sub_buf)
        else:
            buf = p
    if buf:
        chunks.append(buf)
    return [c for c in chunks if c.strip()]


def _concat_wavs(input_paths: list, output_path) -> None:
    """ffmpeg-concat several PCM-WAV chunks into a single WAV.

    All input WAVs share format (F5TTS-Ro returns 24 kHz mono) so the
    cheap ``concat`` demuxer works (no re-encode).
    """
    import subprocess
    from pathlib import Path

    output_path = Path(output_path)
    if len(input_paths) == 1:
        # Single chunk — copy / rename in place.
        import shutil as _sh

        if Path(input_paths[0]) != output_path:
            _sh.copyfile(input_paths[0], output_path)
        return
    listfile = output_path.with_suffix(".concat.txt")
    listfile.write_text(
        "\n".join(f"file '{Path(p).as_posix()}'" for p in input_paths) + "\n",
        encoding="utf-8",
    )
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "concat", "-safe", "0", "-i", str(listfile),
                "-c", "copy", str(output_path),
            ],
            check=True,
            timeout=120,
            capture_output=True,
        )
    finally:
        try:
            listfile.unlink(missing_ok=True)
        except OSError:
            pass


async def _generate_via_f5tts_ro(
    payload: TTSGenerateRequest,
    session: AsyncSession,
) -> TTSGenerateResponse:
    """Phase 10A-1 — route TTS generation to the optional ``tts-ro``
    Docker service over HTTP.

    Phase 12Y — chunking: scripts longer than
    ``F5TTS_RO_CHUNK_MAX_CHARS`` (default 180 chars, ~15 s of speech)
    are split into multiple wrapper calls and the resulting WAVs are
    concatenated with ffmpeg into a single artifact. Removes the
    ~15-second hard limit operators previously hit on F5TTS-Ro.

    Error categorisation:
    - ``tts_runtime_missing`` — wrapper unreachable.
    - ``tts_assets_missing`` — wrapper 404/4xx about model/reference.
    - ``tts_provider_not_configured`` — ``F5TTS_RO_BASE_URL`` unset.
    - ``tts_generation_failed`` — wrapper success but WAV invalid, OR
      ffmpeg concat failure on multi-chunk path.
    """
    import json
    import shutil
    import subprocess
    import urllib.error
    import urllib.parse
    import urllib.request

    provider_id = "f5tts_ro"
    base_url = os.environ.get("F5TTS_RO_BASE_URL", "").strip()
    if not base_url:
        _raise_503(
            "tts_provider_not_configured",
            provider_id,
            "F5TTS-Ro is not configured. Set F5TTS_RO_BASE_URL "
            "(e.g. http://localhost:8061) and start the tts-ro Docker "
            "service. See docs/runbooks/f5tts-ro-runtime.md.",
        )

    voice_id = payload.tts_model or os.environ.get(
        "F5TTS_RO_DEFAULT_VOICE", "ro_default"
    )

    # Pick a destination path under the backend's UPLOAD_AUDIO_ROOT so
    # the audio artifact ends up on the same volume the operator can
    # serve via /api/v1/artifacts/{id}/content.
    root = upload_service.get_upload_root(
        "UPLOAD_AUDIO_ROOT", settings.upload_audio_root
    )
    out_name = upload_service.safe_unique_filename(".wav")
    dest = root / out_name

    # Phase 11F-CDOROB — cross-uid permissions. The backend runs as
    # uid 1000 but the model-tts-ro wrapper runs as uid 10001 to keep
    # the heavy ML container non-root. The audio-upload dir on the
    # shared inputs volume was created by the backend (mode 0755), so
    # F5-TTS inside the wrapper cannot write the output WAV unless we
    # loosen the perms first. Mirrors the SadTalker per-job-dir trick.
    try:
        root.mkdir(parents=True, exist_ok=True)
        root.chmod(0o777)
    except OSError:
        pass

    # Phase 12Y — chunk long scripts. Default chunk size matches the
    # ~15 s F5TTS batch window; operator can tune via env.
    max_chars = int(os.environ.get("F5TTS_RO_CHUNK_MAX_CHARS", "180"))
    chunks = _chunk_script_for_tts(payload.script_text, max_chars=max_chars)
    timeout_s = int(os.environ.get("F5TTS_RO_TIMEOUT", "120"))

    def _call_wrapper(chunk_text: str, chunk_dest):
        """Make ONE call to F5TTS-Ro for ``chunk_text`` → writes to ``chunk_dest``.
        Raises HTTPException via _raise_503 on failure."""
        req_body = {
            "text": chunk_text,
            "voice_id": voice_id,
            "output_path": str(chunk_dest),
            "output_format": "wav",
            "language": payload.language or "ro",
        }
        data = json.dumps(req_body).encode("utf-8")
        url = base_url.rstrip("/") + "/tts/generate"
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                try:
                    body = json.loads(resp.read().decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    _raise_503("tts_generation_failed", provider_id,
                               f"F5TTS-Ro wrapper returned malformed JSON: {exc}")
                http_code = resp.status
        except urllib.error.HTTPError as exc:
            err_text = exc.read().decode("utf-8", errors="replace")[:400]
            if exc.code in (400, 404, 410, 422):
                code = "tts_assets_missing" if "asset" in err_text.lower() or "model" in err_text.lower() else "tts_provider_not_configured"
            else:
                code = "tts_generation_failed"
            _raise_503(code, provider_id, f"F5TTS-Ro wrapper HTTP {exc.code}: {err_text}")
        except urllib.error.URLError as exc:
            _raise_503("tts_runtime_missing", provider_id,
                       f"F5TTS-Ro wrapper unreachable at {base_url!r}: "
                       f"{type(exc).__name__}: {getattr(exc, 'reason', exc)}")
        status = body.get("status") if isinstance(body, dict) else None
        if status != "generated":
            wrapper_code = (body or {}).get("error_code") or "generation_failed"
            wrapper_msg = (body or {}).get("message") or f"unknown wrapper error (status={status!r})"
            mapping = {
                "runtime_missing": "tts_runtime_missing",
                "assets_missing": "tts_assets_missing",
                "config_missing": "tts_provider_not_configured",
                "generation_failed": "tts_generation_failed",
            }
            be_code = mapping.get(str(wrapper_code), "tts_generation_failed")
            try:
                chunk_dest.unlink(missing_ok=True)
            except Exception:
                pass
            _raise_503(be_code, provider_id, f"F5TTS-Ro wrapper: {wrapper_msg}")
        if not chunk_dest.is_file() or chunk_dest.stat().st_size == 0:
            _raise_503("tts_generation_failed", provider_id,
                       f"F5TTS-Ro wrapper reported success but {chunk_dest} is missing/empty.")
        return body, http_code

    # Generate one WAV per chunk, then concat. The final ``dest`` (single
    # artifact path) gets the concatenated result.
    chunk_files: list = []
    wrapper_bodies: list = []
    body = None
    http_code = None
    try:
        if len(chunks) == 1:
            body, http_code = _call_wrapper(chunks[0], dest)
            wrapper_bodies = [body]
        else:
            for i, chunk_text in enumerate(chunks):
                chunk_dest = root / upload_service.safe_unique_filename(f".chunk{i:03d}.wav")
                chunk_body, chunk_http = _call_wrapper(chunk_text, chunk_dest)
                chunk_files.append(chunk_dest)
                wrapper_bodies.append(chunk_body)
                http_code = chunk_http  # last is reported
            # Concat all chunks into the final dest.
            try:
                _concat_wavs(chunk_files, dest)
            except subprocess.CalledProcessError as exc:
                _raise_503("tts_generation_failed", provider_id,
                           f"ffmpeg concat failed: rc={exc.returncode} stderr={(exc.stderr or b'').decode('utf-8', 'replace')[:200]}")
            body = {
                "status": "generated",
                "metadata": {
                    "chunked": True,
                    "chunk_count": len(chunks),
                    "chunk_lengths_chars": [len(c) for c in chunks],
                    "first_chunk_metadata": (wrapper_bodies[0] or {}).get("metadata") or {},
                },
            }
    finally:
        # Clean up chunk files (the concat output is dest, separate).
        for cf in chunk_files:
            try:
                cf.unlink(missing_ok=True)
            except OSError:
                pass

    if not dest.is_file() or dest.stat().st_size == 0:
        _raise_503(
            "tts_generation_failed",
            provider_id,
            f"F5TTS-Ro post-chunk output {dest} is missing/empty.",
        )
    status = "generated"
    try:
        meta = validate_and_inspect_wav(
            dest,
            mime_type="audio/wav",
            max_size_bytes=settings.audio_max_file_size_bytes,
        )
    except ValueError as exc:
        try:
            dest.unlink(missing_ok=True)
        except Exception:
            pass
        _raise_503(
            "tts_generation_failed",
            provider_id,
            f"F5TTS-Ro produced a WAV that failed validation: {exc}",
        )

    metadata_json = {
        "phase": "phase10a1_f5tts_ro",
        "source": "tts_generate",
        "provider_id": provider_id,
        "voice_id": voice_id,
        "language": payload.language or "ro",
        "sample_rate": meta.sample_rate,
        "channels": meta.channels,
        "duration_seconds": meta.duration_seconds,
        "mime_type": "audio/wav",
        # Phase 17G — persist the script text on the audio artifact so a
        # downstream /jobs/from-inputs that uses voice_mode=provided_audio
        # can still emit subtitles without the operator passing
        # script_text in the body.
        "script_text": payload.script_text,
        "f5tts_ro": {
            "base_url": base_url,
            "wrapper_status": status,
            "wrapper_metadata": (body.get("metadata") if isinstance(body, dict) else None) or {},
            "http_code": http_code,
        },
    }
    artifact = await artifact_service.register_artifact(
        session,
        artifact_type=ArtifactType.audio.value,
        uri=dest.as_uri(),
        local_path=str(dest),
        mime_type="audio/wav",
        checksum_sha256=meta.checksum_sha256,
        size_bytes=meta.size_bytes,
        duration_seconds=meta.duration_seconds,
        sample_rate=meta.sample_rate,
        channels=meta.channels,
        metadata_json=metadata_json,
    )
    # Avoid unused-import warnings when the optional shutil/parse paths
    # aren't exercised in this code path.
    _ = (shutil, urllib.parse)
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
