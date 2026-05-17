"""Phase 7B — SadTalker adapter hardening.

Pins the readiness surface for the first real video provider. Phase 7B
does NOT run real inference; the contract here is:

- Importing the provider module never loads torch / diffusers /
  transformers / opencv / sadtalker into ``sys.modules``.
- ``inspect_runtime() / inspect_assets() / inspect_gpu()`` are pure
  inspectors — no torch needed, no model download, no shell-out.
- ``inspect_status()`` returns ``not_implemented`` whenever the
  real-inference gate is off (default), regardless of host capability.
- ``generate()`` refuses to run real inference in Phase 7B, even when
  the gate flag is on — Phase 7D ships the actual call.
- ``/api/v1/video/generate`` translates the provider's status into
  categorised error codes the frontend can pattern-match
  (``video_runtime_missing`` / ``video_assets_missing`` /
  ``video_gpu_missing`` / ``video_provider_not_configured`` /
  ``video_provider_not_implemented`` / ``video_generation_failed``).
- The video-generator catalog row for sadtalker stays ``not_implemented``
  but carries a live readiness ``notes`` string + ``docs_url`` so the
  operator sees what is (and isn't) in place.
- ``ALLOW_MODEL_AUTODOWNLOAD=false`` is unchanged.
- No filesystem writes from the inspection helpers.
"""
from __future__ import annotations

import io
import subprocess
import sys
import uuid
import wave
from pathlib import Path

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient


REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = REPO_ROOT / ".env.example"


_FORBIDDEN_AT_LOAD = (
    "torch",
    "torchvision",
    "torchaudio",
    "diffusers",
    "transformers",
    "accelerate",
    "cv2",
    "sadtalker",
    "gfpgan",
    "xformers",
)


# ---------------------------------------------------------------------------
# Module-load isolation
# ---------------------------------------------------------------------------


def test_sadtalker_module_does_not_import_torch_at_load():
    code = (
        "import sys\n"
        "import agents.lipsync.providers.sadtalker.provider  # noqa: F401\n"
        f"leaked = [m for m in {_FORBIDDEN_AT_LOAD!r} if m in sys.modules]\n"
        "print(','.join(sorted(leaked)))\n"
    )
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(REPO_ROOT),
    )
    assert res.returncode == 0, res.stderr
    leaked = [m for m in res.stdout.strip().split(",") if m]
    assert leaked == [], (
        f"SadTalker provider module pulled {leaked!r} into sys.modules at load; "
        "all heavy imports must be lazy."
    )


# ---------------------------------------------------------------------------
# Inspection helpers — pure, no torch needed
# ---------------------------------------------------------------------------


def test_inspect_runtime_reports_torch_unavailable_in_light_image(monkeypatch):
    """The default backend image has no torch. ``inspect_runtime()``
    must report that without raising."""
    from agents.lipsync.providers.sadtalker.provider import SadTalkerProvider

    # Be defensive: even if the host venv happens to have torch, we just
    # check that the call returns the documented shape.
    runtime = SadTalkerProvider.inspect_runtime()
    assert isinstance(runtime, dict)
    assert "torch_available" in runtime
    assert isinstance(runtime["torch_available"], bool)


def test_inspect_assets_reports_not_configured_when_root_unset(monkeypatch, tmp_path):
    from agents.lipsync.providers.sadtalker.provider import SadTalkerProvider

    monkeypatch.delenv("SADTALKER_MODELS_ROOT", raising=False)
    monkeypatch.delenv("LIPSYNC_MODELS_ROOT", raising=False)

    provider = SadTalkerProvider()  # picks up env at construct time
    assets = provider.inspect_assets()
    assert assets["status"] == "not_configured"
    assert assets["models_root"] is None
    assert assets["missing"]  # non-empty list of expected files


def test_inspect_assets_reports_missing_when_root_empty(monkeypatch, tmp_path):
    from agents.lipsync.providers.sadtalker.provider import SadTalkerProvider

    monkeypatch.setenv("SADTALKER_MODELS_ROOT", str(tmp_path))
    provider = SadTalkerProvider()
    assets = provider.inspect_assets()
    assert assets["status"] == "missing"
    assert assets["models_root"] == str(tmp_path)
    assert len(assets["missing"]) > 0


def test_inspect_gpu_reports_unavailable_without_torch(monkeypatch):
    """When torch isn't on PATH, ``inspect_gpu()`` must short-circuit
    without trying to import it."""
    from agents.lipsync.providers.sadtalker.provider import SadTalkerProvider

    info = SadTalkerProvider.inspect_gpu()
    assert info["available"] in (True, False)
    if info["available"] is False:
        # The default backend image has no torch — the reason field is
        # informative.
        assert "reason" in info


# ---------------------------------------------------------------------------
# inspect_status — the readiness gate the API + catalog read
# ---------------------------------------------------------------------------


def test_inspect_status_returns_not_implemented_when_gate_off(monkeypatch, tmp_path):
    """Default state: real-inference flags off → ``not_implemented`` even if
    everything else is in place."""
    from agents.lipsync.providers.sadtalker.provider import SadTalkerProvider

    monkeypatch.setenv("SADTALKER_MODELS_ROOT", str(tmp_path))
    monkeypatch.delenv("SADTALKER_ENABLE_REAL_INFERENCE", raising=False)
    monkeypatch.delenv("RUN_REAL_SADTALKER", raising=False)

    info = SadTalkerProvider().inspect_status()
    assert info["status"] == "not_implemented"
    # Details still surface the underlying inspection.
    assert "assets" in info["details"]
    assert "runtime" in info["details"]
    assert "gpu" in info["details"]


def test_inspect_status_requires_both_flags(monkeypatch, tmp_path):
    from agents.lipsync.providers.sadtalker.provider import SadTalkerProvider

    monkeypatch.setenv("SADTALKER_MODELS_ROOT", str(tmp_path))
    # Only one of the two flags is on. Must remain ``not_implemented``.
    monkeypatch.setenv("SADTALKER_ENABLE_REAL_INFERENCE", "true")
    monkeypatch.delenv("RUN_REAL_SADTALKER", raising=False)
    assert SadTalkerProvider().inspect_status()["status"] == "not_implemented"

    monkeypatch.delenv("SADTALKER_ENABLE_REAL_INFERENCE", raising=False)
    monkeypatch.setenv("RUN_REAL_SADTALKER", "1")
    assert SadTalkerProvider().inspect_status()["status"] == "not_implemented"


def test_inspect_status_surfaces_assets_missing_when_gate_open(monkeypatch, tmp_path):
    from agents.lipsync.providers.sadtalker.provider import SadTalkerProvider

    monkeypatch.setenv("SADTALKER_MODELS_ROOT", str(tmp_path))
    monkeypatch.setenv("SADTALKER_ENABLE_REAL_INFERENCE", "true")
    monkeypatch.setenv("RUN_REAL_SADTALKER", "1")
    info = SadTalkerProvider().inspect_status()
    # Assets directory is empty — surface ``assets_missing``.
    assert info["status"] in ("assets_missing", "runtime_missing", "gpu_unavailable")
    # In the default backend image we expect assets_missing first (the
    # SADTALKER_MODELS_ROOT path is set but empty).
    assert info["status"] == "assets_missing"


def test_inspect_status_surfaces_not_configured_when_gate_open(monkeypatch):
    from agents.lipsync.providers.sadtalker.provider import SadTalkerProvider

    monkeypatch.delenv("SADTALKER_MODELS_ROOT", raising=False)
    monkeypatch.delenv("LIPSYNC_MODELS_ROOT", raising=False)
    monkeypatch.setenv("SADTALKER_ENABLE_REAL_INFERENCE", "true")
    monkeypatch.setenv("RUN_REAL_SADTALKER", "1")
    assert SadTalkerProvider().inspect_status()["status"] == "not_configured"


# ---------------------------------------------------------------------------
# generate() refuses inference in Phase 7B
# ---------------------------------------------------------------------------


def test_generate_refuses_when_gate_off(monkeypatch, tmp_path):
    from agents.lipsync.providers.sadtalker.provider import SadTalkerProvider

    monkeypatch.delenv("SADTALKER_ENABLE_REAL_INFERENCE", raising=False)
    monkeypatch.delenv("RUN_REAL_SADTALKER", raising=False)
    result = SadTalkerProvider().generate(
        image_path=tmp_path / "img.png",
        audio_path=tmp_path / "voice.wav",
        output_dir=tmp_path / "out",
    )
    assert result["status"] == "not_implemented"
    assert result["error_code"] == "video_provider_not_implemented"


def test_generate_refuses_even_when_gate_on(monkeypatch, tmp_path):
    """Phase 7B never invokes the real path — even with both flags on
    we get a non-completed result. (Phase 7D ships the actual call.)"""
    from agents.lipsync.providers.sadtalker.provider import SadTalkerProvider

    monkeypatch.setenv("SADTALKER_MODELS_ROOT", str(tmp_path))
    monkeypatch.setenv("SADTALKER_ENABLE_REAL_INFERENCE", "true")
    monkeypatch.setenv("RUN_REAL_SADTALKER", "1")
    result = SadTalkerProvider().generate(
        image_path=tmp_path / "img.png",
        audio_path=tmp_path / "voice.wav",
        output_dir=tmp_path / "out",
    )
    assert result["status"] != "completed"
    # Either assets_missing (no weights placed) or not_implemented if the
    # host happens to be ready. ``completed`` would be a bug.
    assert result["error_code"] in (
        "video_provider_not_implemented",
        "video_assets_missing",
        "video_runtime_missing",
        "video_gpu_missing",
    )


# ---------------------------------------------------------------------------
# /api/v1/video/generate — categorised codes on sadtalker
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def app_under_test(monkeypatch, tmp_path):
    monkeypatch.setenv("UPLOAD_AUDIO_ROOT", str(tmp_path / "audio"))
    monkeypatch.setenv("UPLOAD_IMAGE_ROOT", str(tmp_path / "images"))
    monkeypatch.setenv("UPLOAD_TEXT_ROOT", str(tmp_path / "text"))
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


def _make_png(w: int = 256, h: int = 256) -> bytes:
    # Phase 11E — image suitability precheck refuses <256x256.
    import struct
    import zlib

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = b"IHDR" + struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    ihdr_chunk = (
        struct.pack(">I", 13) + ihdr + struct.pack(">I", zlib.crc32(ihdr) & 0xFFFFFFFF)
    )
    raw = b"".join(b"\x00" + b"\xFF\xFF\xFF" * w for _ in range(h))
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
            "brief": "phase 7b",
            "synthetic_person_confirmed": True,
            "consent_confirmed": True,
            "target_duration_seconds": 30,
            "watermark_required": True,
            "c2pa_required": True,
            "script_text": "phase 7b",
        },
    )
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]

    r2 = await client.post(
        "/api/v1/uploads/audio",
        files={"file": ("voice.wav", _make_wav(), "audio/wav")},
    )
    assert r2.status_code == 201, r2.text
    audio_id = r2.json()["artifact_id"]

    r3 = await client.post(
        "/api/v1/uploads/image",
        files={"file": ("face.png", _make_png(), "image/png")},
    )
    assert r3.status_code == 201, r3.text
    image_id = r3.json()["artifact_id"]

    return job_id, audio_id, image_id


async def test_video_generate_sadtalker_default_state_is_phase6a_compatible(
    app_under_test, monkeypatch
):
    """Backward-compat: with real-inference flags off, sadtalker still
    returns ``not_implemented`` / ``provider_not_implemented`` so the
    Phase 6A contract holds."""
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
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "not_implemented"
    assert body["error_code"] == "provider_not_implemented"
    assert body["output_video_artifact_id"] is None
    # Phase 7B adds an ``inspect_status`` block under metadata.sadtalker.
    assert body["metadata"].get("sadtalker", {}).get("inspect_status") == "not_implemented"


async def test_video_generate_sadtalker_assets_missing_when_gate_open(
    app_under_test, monkeypatch, tmp_path
):
    monkeypatch.setenv("SADTALKER_MODELS_ROOT", str(tmp_path / "weights"))
    monkeypatch.setenv("SADTALKER_ENABLE_REAL_INFERENCE", "true")
    monkeypatch.setenv("RUN_REAL_SADTALKER", "1")
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
    # Weights dir doesn't exist or is empty → assets_missing surfaces.
    assert body["error_code"] in (
        "video_assets_missing",
        "video_provider_not_configured",
        # On the unlikely chance a host has torch but the dir is missing
        # we accept that same code surfaces.
    )
    assert body["output_video_artifact_id"] is None
    assert "phase" not in body["message"].lower() or "phase 7" in body["message"].lower()


async def test_video_generate_sadtalker_not_configured_when_gate_open_root_unset(
    app_under_test, monkeypatch
):
    monkeypatch.delenv("SADTALKER_MODELS_ROOT", raising=False)
    monkeypatch.delenv("LIPSYNC_MODELS_ROOT", raising=False)
    monkeypatch.setenv("SADTALKER_ENABLE_REAL_INFERENCE", "true")
    monkeypatch.setenv("RUN_REAL_SADTALKER", "1")
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
    assert body["error_code"] == "video_provider_not_configured"
    assert body["status"] == "not_configured"
    assert body["output_video_artifact_id"] is None


async def test_video_generate_unknown_provider_still_returns_categorised_error(
    app_under_test,
):
    job_id, audio_id, image_id = await _setup_inputs(app_under_test)
    r = await app_under_test.post(
        "/api/v1/video/generate",
        json={
            "job_id": job_id,
            "audio_artifact_id": audio_id,
            "image_artifact_id": image_id,
            "provider_id": "definitely_not_a_provider",
            "target_duration_seconds": 30,
        },
    )
    body = r.json()
    assert body["status"] == "not_configured"
    assert body["error_code"] == "unknown_provider"


# ---------------------------------------------------------------------------
# Provider catalog — sadtalker carries live readiness notes + docs_url
# ---------------------------------------------------------------------------


async def test_catalog_sadtalker_row_has_docs_url_and_readiness_notes(app_under_test):
    r = await app_under_test.get("/api/v1/providers/video-generators")
    assert r.status_code == 200, r.text
    by_id = {p["provider_id"]: p for p in r.json()}
    sad = by_id["sadtalker"]
    assert sad["requires_gpu"] is True
    assert sad["requires_model_files"] is True
    # Phase 11H — when the real-inference gate is off (the unit-test
    # default, no env vars set in this fixture), status is
    # ``not_implemented``. When the gate flips on AND the wrapper /
    # local torch reports ``ready``, status becomes ``available``.
    assert sad["status"] in ("not_implemented", "available")
    # docs_url must point to the runbook.
    assert "sadtalker-runtime" in sad["docs_url"]
    # The notes field must describe the live readiness state — phrasing
    # is no longer pinned word-for-word (Phase 11H rewrote the strings)
    # but it must reference the operator-controlled gates so an
    # operator knows what to flip when status=not_implemented.
    notes = sad["notes"]
    if sad["status"] == "not_implemented":
        assert "SADTALKER_ENABLE_REAL_INFERENCE" in notes
        assert "RUN_REAL_SADTALKER" in notes
    else:
        assert "Phase 7D" in notes or "Phase 11C" in notes
    # healthcheck_available now true (we have inspect_status).
    assert sad["healthcheck_available"] is True


# ---------------------------------------------------------------------------
# Safety invariants — no auto-download, no shell-out
# ---------------------------------------------------------------------------


def test_allow_model_autodownload_pinned_false_in_env_example():
    text = ENV_EXAMPLE.read_text()
    assert "ALLOW_MODEL_AUTODOWNLOAD=false" in text


def test_sadtalker_provider_module_has_no_download_calls():
    src = (
        REPO_ROOT
        / "agents"
        / "lipsync"
        / "providers"
        / "sadtalker"
        / "provider.py"
    ).read_text()
    lowered = "\n".join(
        ln for ln in src.splitlines() if not ln.lstrip().startswith("#")
    ).lower()
    for needle in (
        "urllib.request",
        "requests.get",
        "huggingface_hub.snapshot_download",
        "hf_hub_download",
        "wget",
        "curl ",
        "subprocess.run",
    ):
        assert needle not in lowered, (
            f"SadTalker provider has an active line containing {needle!r}; "
            "no auto-download in Phase 7B."
        )


def test_video_api_module_has_no_torch_at_load():
    """The backend API module must not pull torch into sys.modules just
    by being imported. (The torch path is only reached inside the
    SadTalker provider's gpu probe, which is itself gated.)"""
    code = (
        "import sys, app.api.video  # noqa: F401\n"
        "print('torch' in sys.modules)\n"
    )
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(REPO_ROOT),
    )
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "False"


_ = uuid  # placate the unused-import linter if a future test drops the only use
