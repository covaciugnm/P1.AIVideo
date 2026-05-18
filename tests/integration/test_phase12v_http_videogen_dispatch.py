"""Phase 12V — HTTP dispatch table for text-to-video / image-to-video wrappers.

What this phase pins:

- ``_HTTP_VIDEOGEN_DISPATCH`` exposes 5 entries (svd, animatediff,
  ltx_video, hunyuan_video, mochi) with two input kinds:
    * ``image_only`` (svd) — uses the upstream face portrait
    * ``prompt_only`` (animatediff/ltx/hunyuan/mochi) — uses script_text
- When the corresponding ``<NAME>_BASE_URL`` env var is unset, the
  handler falls through to the Phase 3A no-op stub.
- When the env var IS set + the wrapper returns ``completed``, the
  handler registers the MP4 as a ``talking_head`` ArtifactRef.
- When the wrapper returns a categorised failure, the handler raises
  ``StageRejection`` with ``<error_code>: <provider> <message>``.
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


def _build_state(provider_id: str, *, face_path: str, voice_path: str, script_text: str = "Test prompt"):
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
        brief="phase 12v brief fallback",
        target_duration_seconds=20,
        synthetic_person_confirmed=True,
        consent_confirmed=True,
        watermark_required=True,
        c2pa_required=True,
        script_text=script_text,
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


def test_videogen_dispatch_table_lists_expected_providers():
    assert set(lipsync_handler._HTTP_VIDEOGEN_DISPATCH) == {
        "svd", "animatediff", "ltx_video", "hunyuan_video", "mochi",
    }
    image_only = {pid for pid, spec in lipsync_handler._HTTP_VIDEOGEN_DISPATCH.items()
                  if spec["input_kind"] == "image_only"}
    prompt_only = {pid for pid, spec in lipsync_handler._HTTP_VIDEOGEN_DISPATCH.items()
                   if spec["input_kind"] == "prompt_only"}
    assert image_only == {"svd"}
    assert prompt_only == {"animatediff", "ltx_video", "hunyuan_video", "mochi"}


def test_videogen_prompt_helper_truncates_and_falls_back_to_brief():
    from common.schemas import DagState

    state = DagState(
        job_id=uuid.uuid4(),
        brief="fallback brief text",
        target_duration_seconds=10,
        synthetic_person_confirmed=True,
        consent_confirmed=True,
        watermark_required=True,
        c2pa_required=True,
        script_text=None,
    )
    assert lipsync_handler._resolve_videogen_prompt(state) == "fallback brief text"

    state.script_text = "x" * 5000
    out = lipsync_handler._resolve_videogen_prompt(state)
    assert len(out) == 4000


@pytest.mark.asyncio
async def test_videogen_falls_through_when_wrapper_url_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("ANIMATEDIFF_BASE_URL", raising=False)
    face = tmp_path / "f.png"; face.write_bytes(b"\x89PNG\r\n\x1a\n")
    voice = tmp_path / "v.wav"; voice.write_bytes(b"RIFF0000WAVE")

    state = _build_state("animatediff", face_path=str(face), voice_path=str(voice))
    out = await lipsync_handler.run(state, signing_key="TEST-KEY", expected_backend="sadtalker")
    assert out.noop is True


@pytest.mark.asyncio
async def test_videogen_prompt_only_dispatch_success(monkeypatch, tmp_path):
    monkeypatch.setenv("ANIMATEDIFF_BASE_URL", "http://fake-animatediff:8080")
    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path / "artifacts"))
    face = tmp_path / "f.png"; face.write_bytes(b"\x89PNG\r\n\x1a\n")
    voice = tmp_path / "v.wav"; voice.write_bytes(b"RIFF0000WAVE")

    class _R:
        def __init__(self, b): self.b = b
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self): return self.b

    captured = {}
    def _fake_urlopen(req, timeout=None):
        body = json.loads(req.data.decode("utf-8"))
        captured.update(body)
        out_path = Path(body["output_path"])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"FAKEMP4DATA" * 64)
        return _R(json.dumps({
            "status": "completed",
            "output_path": str(out_path),
            "duration_seconds": 2.0,
            "fps": 8,
            "num_frames": 16,
        }).encode("utf-8"))

    state = _build_state("animatediff",
                          face_path=str(face), voice_path=str(voice),
                          script_text="A cinematic shot of a person speaking")
    with patch("urllib.request.urlopen", _fake_urlopen):
        out = await lipsync_handler.run(state, signing_key="TEST-KEY", expected_backend="sadtalker")

    assert out.noop is False
    ref = out.artifacts["talking_head"]
    assert ref.artifact_type == "video"
    assert ref.size_bytes > 0
    assert captured["prompt"] == "A cinematic shot of a person speaking"
    assert "image_path" not in captured  # prompt_only doesn't send an image
    assert "audio_path" not in captured  # text-to-video doesn't take audio
    assert out.extra["animatediff"]["input_kind"] == "prompt_only"


@pytest.mark.asyncio
async def test_videogen_image_only_dispatch_uses_portrait(monkeypatch, tmp_path):
    """SVD takes just the face portrait; no prompt, no audio."""
    monkeypatch.setenv("SVD_BASE_URL", "http://fake-svd:8080")
    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path / "artifacts"))
    face = tmp_path / "f.png"; face.write_bytes(b"\x89PNG\r\n\x1a\n")
    voice = tmp_path / "v.wav"; voice.write_bytes(b"RIFF0000WAVE")

    class _R:
        def __init__(self, b): self.b = b
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self): return self.b

    captured = {}
    def _fake_urlopen(req, timeout=None):
        body = json.loads(req.data.decode("utf-8"))
        captured.update(body)
        out_path = Path(body["output_path"])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"SVD-MP4-DATA" * 32)
        return _R(json.dumps({
            "status": "completed",
            "output_path": str(out_path),
            "num_frames": 25, "fps": 7,
        }).encode("utf-8"))

    state = _build_state("svd", face_path=str(face), voice_path=str(voice))
    with patch("urllib.request.urlopen", _fake_urlopen):
        out = await lipsync_handler.run(state, signing_key="TEST-KEY", expected_backend="sadtalker")

    assert out.noop is False
    assert out.artifacts["talking_head"].size_bytes > 0
    assert captured["image_path"] == str(face)
    assert "prompt" not in captured
    assert "audio_path" not in captured


@pytest.mark.asyncio
async def test_videogen_failure_translates_to_stage_rejection(monkeypatch, tmp_path):
    from common.exceptions import StageRejection

    monkeypatch.setenv("HUNYUAN_BASE_URL", "http://fake-hunyuan:8080")
    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path / "artifacts"))
    face = tmp_path / "f.png"; face.write_bytes(b"\x89PNG\r\n\x1a\n")
    voice = tmp_path / "v.wav"; voice.write_bytes(b"RIFF0000WAVE")

    class _R:
        def __init__(self, b): self.b = b
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self): return self.b

    def _fake_urlopen(req, timeout=None):
        return _R(json.dumps({
            "status": "gpu_unavailable",
            "error_code": "video_gpu_missing",
            "message": "no CUDA device visible",
        }).encode("utf-8"))

    state = _build_state("hunyuan_video", face_path=str(face), voice_path=str(voice))
    with patch("urllib.request.urlopen", _fake_urlopen):
        with pytest.raises(StageRejection) as exc:
            await lipsync_handler.run(state, signing_key="TEST-KEY", expected_backend="sadtalker")
    assert "video_gpu_missing" in str(exc.value)
    assert "hunyuan_video" in str(exc.value)
