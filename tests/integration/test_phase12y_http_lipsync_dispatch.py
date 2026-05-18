"""Phase 12Y — HTTP dispatch table for the new lipsync wrappers.

What this phase pins:

- The lipsync handler exposes a ``_HTTP_LIPSYNC_DISPATCH`` table with
  entries for sadtalker + 4 new providers (wav2lip, musetalk,
  echomimic, hallo). LivePortrait is intentionally absent (driving
  video, not audio).
- When the corresponding ``<NAME>_BASE_URL`` env var is **unset**, the
  handler preserves the Phase 3A no-op stub for every non-sadtalker
  provider — no StageRejection, the job pipeline keeps moving.
- When the env var IS set and the wrapper returns a successful
  ``{"status": "completed", "output_path": ...}`` payload, the handler
  registers a ``talking_head`` ``ArtifactRef`` with the wrapper's MP4.
- When the wrapper returns a categorised failure
  (``{"status": "generation_failed", "error_code": ..., "message": ...}``),
  the handler raises ``StageRejection`` with the same
  ``<error_code>: <message>`` shape as SadTalker.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from agents.lipsync import handler as lipsync_handler


def _build_state(provider_id: str, *, face_path: str, voice_path: str):
    from agents.compliance_officer.compliance_token import mint_token
    from common.schemas import (
        ArtifactRef,
        ComplianceTokenClaims,
        DagState,
        StageOutput,
    )

    job_id = uuid.uuid4()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    claims = ComplianceTokenClaims(
        job_id=str(job_id),
        synthetic_person_confirmed=True,
        consent_confirmed=True,
        watermark_required=True,
        c2pa_required=True,
        allowed_lipsync_backend="sadtalker",
        issued_at=now,
        expires_at=now.replace(year=now.year + 1),
    )
    token = mint_token(claims, "TEST-KEY")
    state = DagState(
        job_id=job_id,
        brief="phase 12y",
        target_duration_seconds=20,
        synthetic_person_confirmed=True,
        consent_confirmed=True,
        watermark_required=True,
        c2pa_required=True,
        compliance_token=token,
        provider_selection={"video_provider_id": provider_id},
    )
    state.stage_outputs["face"] = StageOutput(
        artifacts={
            "portrait": ArtifactRef(
                artifact_type="image",
                uri=f"file://{face_path}",
                local_path=face_path,
            )
        }
    )
    state.stage_outputs["voice"] = StageOutput(
        artifacts={
            "narration": ArtifactRef(
                artifact_type="audio",
                uri=f"file://{voice_path}",
                local_path=voice_path,
            )
        }
    )
    return state


def test_dispatch_table_lists_expected_providers():
    """Catalog regression — adding/removing a wrapper without updating
    the dispatch table (or vice versa) would break this assertion."""
    assert set(lipsync_handler._HTTP_LIPSYNC_DISPATCH) == {
        "sadtalker", "wav2lip", "musetalk", "echomimic", "hallo",
    }
    for pid, spec in lipsync_handler._HTTP_LIPSYNC_DISPATCH.items():
        assert spec["env_url"].endswith("_BASE_URL")
        assert spec["env_timeout"].endswith("_HTTP_TIMEOUT")
        assert spec["endpoint"].startswith("/")
        assert spec["endpoint"].endswith("/generate")
        assert isinstance(spec["default_timeout"], int) and spec["default_timeout"] >= 600


@pytest.mark.asyncio
async def test_lipsync_falls_through_when_wrapper_url_unset(monkeypatch, tmp_path):
    """A new wrapper provider without its BASE_URL env still returns a
    no-op stub. The lipsync stage must not block the job pipeline just
    because an opt-in wrapper hasn't been brought up."""
    monkeypatch.delenv("MUSETALK_BASE_URL", raising=False)

    face = tmp_path / "face.png"; face.write_bytes(b"\x89PNG\r\n\x1a\n")
    voice = tmp_path / "voice.wav"; voice.write_bytes(b"RIFF0000WAVEfmt ")

    state = _build_state("musetalk", face_path=str(face), voice_path=str(voice))
    out = await lipsync_handler.run(state, signing_key="TEST-KEY", expected_backend="sadtalker")
    assert out.noop is True
    assert "musetalk" not in out.extra


@pytest.mark.asyncio
async def test_lipsync_dispatch_http_success(monkeypatch, tmp_path):
    """When MUSETALK_BASE_URL is set + the wrapper returns ``completed``,
    the handler registers the wrapper's MP4 as a talking_head ArtifactRef."""
    monkeypatch.setenv("MUSETALK_BASE_URL", "http://fake-musetalk:8080")
    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path / "artifacts"))

    face = tmp_path / "face.png"; face.write_bytes(b"\x89PNG\r\n\x1a\n")
    voice = tmp_path / "voice.wav"; voice.write_bytes(b"RIFF0000WAVEfmt ")

    # The wrapper writes the MP4 at the output_path the handler picks.
    # Patch urlopen so we don't actually do HTTP; we still write a real
    # file at the path the body says, so the handler's stat() succeeds.
    class _FakeResp:
        def __init__(self, payload: bytes): self._payload = payload
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self): return self._payload

    captured = {}
    def _fake_urlopen(req, timeout=None):
        body = json.loads(req.data.decode("utf-8"))
        captured.update(body)
        out_path = Path(body["output_path"])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"\x00\x00\x00\x18ftypisomMP4DATA" * 128)
        return _FakeResp(json.dumps({
            "status": "completed",
            "output_path": str(out_path),
            "size_bytes": out_path.stat().st_size,
            "duration_seconds": 7.5,
            "fps": 25,
        }).encode("utf-8"))

    with patch("urllib.request.urlopen", _fake_urlopen):
        state = _build_state("musetalk", face_path=str(face), voice_path=str(voice))
        out = await lipsync_handler.run(state, signing_key="TEST-KEY", expected_backend="sadtalker")

    assert out.noop is False
    assert "talking_head" in out.artifacts
    ref = out.artifacts["talking_head"]
    assert ref.artifact_type == "video"
    assert ref.mime_type == "video/mp4"
    assert ref.size_bytes > 0
    assert ref.checksum_sha256 == hashlib.sha256(Path(ref.local_path).read_bytes()).hexdigest()
    assert out.extra["musetalk"]["wrapper_endpoint"] == "/musetalk/generate"
    # The handler must have invoked the MUSETALK base URL, not SadTalker's.
    assert captured["image_path"] == str(face)
    assert captured["audio_path"] == str(voice)


@pytest.mark.asyncio
async def test_lipsync_dispatch_http_failure_translates_to_stage_rejection(monkeypatch, tmp_path):
    """When the wrapper returns a categorised failure, the handler
    converts it to a StageRejection with ``<error_code>: <provider> <message>``."""
    from common.exceptions import StageRejection

    monkeypatch.setenv("WAV2LIP_BASE_URL", "http://fake-wav2lip:8080")
    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path / "artifacts"))

    face = tmp_path / "face.png"; face.write_bytes(b"\x89PNG\r\n\x1a\n")
    voice = tmp_path / "voice.wav"; voice.write_bytes(b"RIFF0000WAVEfmt ")

    class _FakeResp:
        def __init__(self, payload: bytes): self._payload = payload
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self): return self._payload

    def _fake_urlopen(req, timeout=None):
        return _FakeResp(json.dumps({
            "status": "generation_failed",
            "error_code": "video_assets_missing",
            "message": "wav2lip_gan.pth not found",
        }).encode("utf-8"))

    with patch("urllib.request.urlopen", _fake_urlopen):
        state = _build_state("wav2lip", face_path=str(face), voice_path=str(voice))
        with pytest.raises(StageRejection) as exc_info:
            await lipsync_handler.run(state, signing_key="TEST-KEY", expected_backend="sadtalker")

    assert "video_assets_missing" in str(exc_info.value)
    assert "wav2lip" in str(exc_info.value)
