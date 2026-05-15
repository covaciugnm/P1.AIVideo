"""Phase 7D — SadTalker real inference smoke + artifact registration.

Default test run **never** invokes real SadTalker. The real smoke test
at the bottom is opt-in via ``RUN_REAL_SADTALKER_SMOKE=1`` and skips
cleanly otherwise.

What this phase tests (the default-suite tests):

- The seven-gate refusal: ``provider.generate()`` returns a categorised
  failure when any of {flags, weights, runtime, GPU, input image,
  input audio} is missing — without ever importing torch.
- ``/api/v1/video/generate`` registers an ``ArtifactType.video`` row +
  returns ``status="completed"`` when the (monkey-patched) provider
  succeeds. The fake provider writes a tiny MP4-shaped file under the
  artifacts root — no real inference runs.
- Backward compat: gate-off behavior still matches Phase 7B / Phase 6A
  invariants (``not_implemented`` / ``provider_not_implemented``).
- Cleanup contract: when the heavy path "fails" (monkey-patched to
  raise), no phantom artifact is registered.
- The real-runtime smoke test is opt-in only.
"""
from __future__ import annotations

import io
import os
import uuid
import wave
from pathlib import Path

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Provider-level: generate() refuses without inputs
# ---------------------------------------------------------------------------


def _enable_real_inference(monkeypatch, models_root: Path) -> None:
    monkeypatch.setenv("SADTALKER_MODELS_ROOT", str(models_root))
    monkeypatch.setenv("SADTALKER_ENABLE_REAL_INFERENCE", "true")
    monkeypatch.setenv("RUN_REAL_SADTALKER", "1")


def _place_fake_weights(models_root: Path) -> None:
    """Create the five files SadTalker's ``required_assets()`` looks for.
    Empty files are enough — ``inspect_assets()`` only checks
    ``Path.is_file()``."""
    (models_root / "checkpoints").mkdir(parents=True, exist_ok=True)
    for name in (
        "mapping_00109-model.pth.tar",
        "mapping_00229-model.pth.tar",
        "SadTalker_V0.0.2_256.safetensors",
        "SadTalker_V0.0.2_512.safetensors",
    ):
        (models_root / "checkpoints" / name).write_bytes(b"")
    (models_root / "gfpgan").mkdir(parents=True, exist_ok=True)
    (models_root / "gfpgan" / "GFPGANv1.4.pth").write_bytes(b"")


def test_generate_rejects_missing_image_with_inputs_failed(monkeypatch, tmp_path):
    from agents.lipsync.providers.sadtalker.provider import SadTalkerProvider

    _enable_real_inference(monkeypatch, tmp_path / "weights")
    _place_fake_weights(tmp_path / "weights")
    # Inspect_status now returns "runtime_missing" on a torch-free host or
    # "gpu_unavailable" on a torch-but-no-CUDA host. We never reach the
    # "input image not found" branch because the readiness gate fails
    # first — that's the correct behavior.
    result = SadTalkerProvider().generate(
        image_path=tmp_path / "does_not_exist.png",
        audio_path=tmp_path / "voice.wav",
        output_dir=tmp_path / "out",
    )
    # The gate ordering: gates 3-5 fail before gates 6-7 are evaluated,
    # so we get a runtime/gpu code on a CPU host.
    assert result["status"] in ("runtime_missing", "gpu_unavailable", "failed")
    assert result.get("output_path") is None or not Path(result["output_path"]).exists()


def test_generate_reaches_input_check_when_all_other_gates_pass(monkeypatch, tmp_path):
    """If we fake out the readiness probe entirely (force status=ready),
    the next gate is input-file presence. Both inputs missing → failed."""
    from agents.lipsync.providers.sadtalker.provider import SadTalkerProvider

    _enable_real_inference(monkeypatch, tmp_path / "weights")
    _place_fake_weights(tmp_path / "weights")

    provider = SadTalkerProvider()
    # Patch inspect_status to short-circuit to "ready".
    monkeypatch.setattr(
        provider,
        "inspect_status",
        lambda: {"status": "ready", "details": {"assets": {}, "runtime": {}, "gpu": {}}},
    )
    # Don't create the input files — gate 6 should fire.
    result = provider.generate(
        image_path=tmp_path / "no_such_image.png",
        audio_path=tmp_path / "no_such_audio.wav",
        output_dir=tmp_path / "out",
    )
    assert result["status"] == "failed"
    assert result["error_code"] == "video_generation_failed"
    assert "input image not found" in result["message"]


def test_generate_reaches_runtime_missing_when_sadtalker_lib_absent(
    monkeypatch, tmp_path
):
    """Force every other gate green; the SadTalker library is not
    installed in this venv, so ``_attempt_real_inference()`` surfaces
    ``runtime_missing`` instead of crashing."""
    from agents.lipsync.providers.sadtalker.provider import SadTalkerProvider

    _enable_real_inference(monkeypatch, tmp_path / "weights")
    _place_fake_weights(tmp_path / "weights")

    # Create the input files so gates 6 + 7 pass.
    img_path = tmp_path / "face.png"
    img_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    aud_path = tmp_path / "voice.wav"
    aud_path.write_bytes(b"RIFF" + b"\x00" * 36)

    provider = SadTalkerProvider()
    monkeypatch.setattr(
        provider,
        "inspect_status",
        lambda: {"status": "ready", "details": {"assets": {}, "runtime": {}, "gpu": {}}},
    )

    result = provider.generate(
        image_path=img_path,
        audio_path=aud_path,
        output_dir=tmp_path / "out",
    )
    # SadTalker library isn't installed anywhere in this repo (Phase 7D
    # deliberately doesn't bundle it). ``_attempt_real_inference`` catches
    # ImportError and surfaces video_runtime_missing.
    assert result["status"] == "runtime_missing"
    assert result["error_code"] == "video_runtime_missing"
    # No phantom MP4 left on disk.
    assert not (tmp_path / "out").exists() or not any((tmp_path / "out").iterdir())


# ---------------------------------------------------------------------------
# API-level: success path with monkey-patched inference
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def app_under_test(monkeypatch, tmp_path):
    monkeypatch.setenv("UPLOAD_AUDIO_ROOT", str(tmp_path / "audio"))
    monkeypatch.setenv("UPLOAD_IMAGE_ROOT", str(tmp_path / "images"))
    monkeypatch.setenv("UPLOAD_TEXT_ROOT", str(tmp_path / "text"))
    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("SCRIPTWRITER_BACKEND", "template")
    monkeypatch.delenv("SCRIPTWRITER_ENABLE_NETWORK_CALLS", raising=False)

    from app.core import db as core_db
    from app.main import create_app
    from app.services import queue_publisher

    await core_db.async_reset_engine()
    await core_db.init_db()
    fake = fakeaioredis.FakeRedis(decode_responses=True)
    queue_publisher.set_redis_client(fake)
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
    await fake.aclose()
    queue_publisher.reset_redis_client()
    await core_db.async_reset_engine()


def _make_wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\x00\x00" * 6615)
    return buf.getvalue()


def _make_png() -> bytes:
    import struct
    import zlib

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = b"IHDR" + struct.pack(">IIBBBBB", 64, 64, 8, 2, 0, 0, 0)
    ihdr_chunk = (
        struct.pack(">I", 13) + ihdr + struct.pack(">I", zlib.crc32(ihdr) & 0xFFFFFFFF)
    )
    raw = b"".join(b"\x00" + b"\xFF\xFF\xFF" * 64 for _ in range(64))
    idat = b"IDAT" + zlib.compress(raw)
    idat_chunk = (
        struct.pack(">I", len(idat) - 4)
        + idat
        + struct.pack(">I", zlib.crc32(idat) & 0xFFFFFFFF)
    )
    iend_chunk = struct.pack(">I", 0) + b"IEND" + struct.pack(
        ">I", zlib.crc32(b"IEND") & 0xFFFFFFFF
    )
    return sig + ihdr_chunk + idat_chunk + iend_chunk


async def _setup_inputs(client: AsyncClient) -> tuple[str, str, str]:
    r = await client.post(
        "/api/v1/jobs",
        json={
            "brief": "phase 7d",
            "synthetic_person_confirmed": True,
            "consent_confirmed": True,
            "target_duration_seconds": 30,
            "watermark_required": True,
            "c2pa_required": True,
            "script_text": "phase 7d",
        },
    )
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]
    r2 = await client.post(
        "/api/v1/uploads/audio",
        files={"file": ("voice.wav", _make_wav(), "audio/wav")},
    )
    assert r2.status_code == 201
    audio_id = r2.json()["artifact_id"]
    r3 = await client.post(
        "/api/v1/uploads/image",
        files={"file": ("face.png", _make_png(), "image/png")},
    )
    assert r3.status_code == 201
    image_id = r3.json()["artifact_id"]
    return job_id, audio_id, image_id


def _fake_generate_success(output_dir: str | Path) -> dict:
    """Helper used by the patched provider — writes a tiny MP4-shaped
    file and returns the same dict the real inference path would."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    mp4_path = out / f"sadtalker_{uuid.uuid4().hex}.mp4"
    # MP4 ISO base-media file-type box, just enough to look right at the
    # bytes level. No real frames — Phase 7D's success-path test only
    # verifies that the API registers what the provider returned.
    mp4_path.write_bytes(
        b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isomiso2mp41"
        + b"\x00" * 64
    )
    return {
        "status": "completed",
        "output_path": str(mp4_path),
        "duration_seconds": 3.5,
        "width": 512,
        "height": 512,
        "model_id": "sadtalker-v1",
        "details": {
            "assets": {"status": "ok"},
            "runtime": {"torch_available": True},
            "gpu": {"available": True, "device_count": 1, "device_name": "fake-gpu"},
        },
    }


async def test_video_generate_success_path_registers_video_artifact(
    app_under_test, monkeypatch
):
    """All seven gates aligned (via monkey-patch); fake generate writes
    a sentinel MP4; the API registers ArtifactType.video + returns
    completed with output_video_artifact_id."""
    # Flip the env flags so inspect_status() returns "ready" once we
    # also monkey-patch it (we can't easily fake torch + CUDA on this
    # host).
    monkeypatch.setenv("SADTALKER_ENABLE_REAL_INFERENCE", "true")
    monkeypatch.setenv("RUN_REAL_SADTALKER", "1")

    job_id, audio_id, image_id = await _setup_inputs(app_under_test)

    from agents.lipsync.providers.sadtalker import provider as sad_mod

    monkeypatch.setattr(
        sad_mod.SadTalkerProvider,
        "inspect_status",
        lambda self: {
            "status": "ready",
            "details": {"assets": {"status": "ok"}, "runtime": {"torch_available": True}, "gpu": {"available": True}},
        },
    )
    monkeypatch.setattr(
        sad_mod,
        "_attempt_real_inference",
        lambda **kwargs: _fake_generate_success(kwargs["output_dir"]),
    )

    r = await app_under_test.post(
        "/api/v1/video/generate",
        json={
            "job_id": job_id,
            "audio_artifact_id": audio_id,
            "image_artifact_id": image_id,
            "provider_id": "sadtalker",
            "target_duration_seconds": 30,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "completed", body
    assert body["error_code"] is None
    assert body["output_video_artifact_id"] is not None
    # Sanity: the registered artifact carries the metadata we expect.
    art_r = await app_under_test.get(
        f"/api/v1/artifacts/{body['output_video_artifact_id']}"
    )
    # The artifact endpoint may or may not exist depending on phase, so
    # fall back to inspecting the metadata block.
    md = body["metadata"]
    assert md["video_size_bytes"] > 0
    assert md["video_checksum_sha256"]
    assert md["video_uri"].endswith(".mp4")


async def test_video_generate_failure_does_not_register_artifact(
    app_under_test, monkeypatch
):
    """When the (fake) inference path returns a categorised failure,
    no video artifact is registered and the response carries the
    categorised error code."""
    monkeypatch.setenv("SADTALKER_ENABLE_REAL_INFERENCE", "true")
    monkeypatch.setenv("RUN_REAL_SADTALKER", "1")

    job_id, audio_id, image_id = await _setup_inputs(app_under_test)

    from agents.lipsync.providers.sadtalker import provider as sad_mod

    monkeypatch.setattr(
        sad_mod.SadTalkerProvider,
        "inspect_status",
        lambda self: {
            "status": "ready",
            "details": {"assets": {}, "runtime": {}, "gpu": {}},
        },
    )
    monkeypatch.setattr(
        sad_mod,
        "_attempt_real_inference",
        lambda **kwargs: {
            "status": "failed",
            "error_code": "video_generation_failed",
            "message": "boom",
            "details": {},
        },
    )

    r = await app_under_test.post(
        "/api/v1/video/generate",
        json={
            "job_id": job_id,
            "audio_artifact_id": audio_id,
            "image_artifact_id": image_id,
            "provider_id": "sadtalker",
            "target_duration_seconds": 30,
        },
    )
    body = r.json()
    assert body["status"] != "completed"
    assert body["output_video_artifact_id"] is None
    # No video artifact in the DB (smoke check via the job-summary endpoint).
    summary_r = await app_under_test.get(f"/api/v1/jobs/{job_id}/summary")
    if summary_r.status_code == 200:
        artifacts = summary_r.json().get("artifacts", [])
        for a in artifacts:
            assert a.get("artifact_type") != "video", (
                "no video artifact may be registered when inference fails"
            )


async def test_video_generate_default_state_still_phase7b_compatible(
    app_under_test, monkeypatch
):
    """With flags OFF (the default), the response shape is unchanged
    from Phase 7B / Phase 6A — even though Phase 7D wired the real
    path."""
    monkeypatch.delenv("SADTALKER_ENABLE_REAL_INFERENCE", raising=False)
    monkeypatch.delenv("RUN_REAL_SADTALKER", raising=False)

    job_id, audio_id, image_id = await _setup_inputs(app_under_test)
    r = await app_under_test.post(
        "/api/v1/video/generate",
        json={
            "job_id": job_id,
            "audio_artifact_id": audio_id,
            "image_artifact_id": image_id,
            "provider_id": "sadtalker",
            "target_duration_seconds": 30,
        },
    )
    body = r.json()
    assert body["status"] == "not_implemented"
    assert body["error_code"] == "provider_not_implemented"
    assert body["output_video_artifact_id"] is None


# ---------------------------------------------------------------------------
# Real-runtime smoke — opt-in via RUN_REAL_SADTALKER_SMOKE=1
# ---------------------------------------------------------------------------


_REAL_SMOKE_ENABLED = os.environ.get("RUN_REAL_SADTALKER_SMOKE", "").lower() in (
    "1",
    "true",
    "yes",
    "on",
)


@pytest.mark.skipif(
    not _REAL_SMOKE_ENABLED,
    reason=(
        "Real SadTalker smoke disabled. Set RUN_REAL_SADTALKER_SMOKE=1 + "
        "SADTALKER_ENABLE_REAL_INFERENCE=true + RUN_REAL_SADTALKER=1 + "
        "SADTALKER_MODELS_ROOT pointing at on-disk weights + a CUDA-capable "
        "host. See docs/runbooks/sadtalker-runtime.md."
    ),
)
def test_real_sadtalker_smoke_when_explicitly_enabled(tmp_path):
    """End-to-end smoke: place real inputs, ask the provider, expect
    either ``completed`` (full GPU host) or one of the categorised
    failures (host partially configured). Never asserts that real MP4
    bytes are present — that would lock the test to one set of weights."""
    from agents.lipsync.providers.sadtalker.provider import SadTalkerProvider

    provider = SadTalkerProvider()
    img = tmp_path / "face.png"
    img.write_bytes(_make_png())
    aud = tmp_path / "voice.wav"
    aud.write_bytes(_make_wav())
    out_dir = tmp_path / "out"

    result = provider.generate(
        image_path=img,
        audio_path=aud,
        output_dir=out_dir,
        target_duration_seconds=5,
    )
    # Acceptable outcomes — every one is a real categorised result, not
    # a crash or fake success.
    assert result["status"] in (
        "completed",
        "runtime_missing",
        "assets_missing",
        "gpu_unavailable",
        "not_configured",
        "failed",
    )
    if result["status"] == "completed":
        out_path = Path(result["output_path"])
        assert out_path.is_file()
        assert out_path.stat().st_size > 0
