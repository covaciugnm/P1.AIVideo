"""Phase 7A — GPU runtime planning invariants.

This phase plans, does not execute. The tests here pin the contract that
keeps GPU-only code paths and weights *out* of the default light stack:

- The video-generator catalog advertises GPU/model-files requirements
  exactly as documented, so the operator UI never lies about cost.
- ``/api/v1/video/generate`` still returns metadata-only ``not_implemented``
  for every GPU placeholder (no inference yet).
- The default Docker light compose excludes every CUDA agent — they are
  gated behind ``--profile gpu``.
- The GPU compose overlay declares NVIDIA device reservations on every
  CUDA agent and on the optional ``model-llm`` (llm profile).
- ``backend/pyproject.toml`` does not pull in torch / diffusers / xformers
  and the live ``app`` import does not transitively load them.
- ``agents`` base install does not pull in torch / diffusers / xformers.
- ``docker/agents/Dockerfile.cuda`` remains a Phase 0 stub — no torch
  install lines, no model download lines.

If any of these break, GPU concerns have leaked into the default stack
and the phase 7A constraint ("no real GPU integration yet") has been
violated. Fix the leak, then update this test only if the constraint
itself has explicitly changed.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_DEV = REPO_ROOT / "docker" / "compose.dev.yml"
COMPOSE_GPU = REPO_ROOT / "docker" / "compose.gpu.yml"
DOCKERFILE_CUDA = REPO_ROOT / "docker" / "agents" / "Dockerfile.cuda"
BACKEND_PYPROJECT = REPO_ROOT / "backend" / "pyproject.toml"
AGENTS_PYPROJECT = REPO_ROOT / "agents" / "pyproject.toml"


_GPU_PLACEHOLDERS = ("sadtalker", "musetalk", "wav2lip", "liveportrait")
_NON_GPU_VIDEO = ("local_http_video", "external_video_api")
_CUDA_AGENTS = ("agent-voice", "agent-face", "agent-lipsync")


# ---------------------------------------------------------------------------
# App fixture (no GPU, no model files, template scriptwriter).
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


# ---------------------------------------------------------------------------
# Catalog invariants
# ---------------------------------------------------------------------------


async def test_video_catalog_marks_gpu_placeholders_correctly(app_under_test):
    """GPU placeholders advertise GPU+model-files; non-GPU stubs do not."""
    r = await app_under_test.get("/api/v1/providers/video-generators")
    assert r.status_code == 200, r.text
    by_id = {p["provider_id"]: p for p in r.json()}

    for pid in _GPU_PLACEHOLDERS:
        info = by_id[pid]
        assert info["requires_gpu"] is True, f"{pid} must declare requires_gpu"
        assert info["requires_model_files"] is True, (
            f"{pid} must declare requires_model_files — operators need to know "
            "they have to fetch weights before this provider can ever run"
        )
        assert info["status"] == "not_implemented", (
            f"{pid} must stay not_implemented until a phase explicitly wires it"
        )

    for pid in _NON_GPU_VIDEO:
        info = by_id[pid]
        assert info["requires_gpu"] is False, (
            f"{pid} is not local GPU inference; must not advertise GPU"
        )
        assert info["requires_model_files"] is False


async def test_video_catalog_set_is_pinned(app_under_test):
    """No silent additions or drops; Phase 7B decisions need a stable baseline."""
    r = await app_under_test.get("/api/v1/providers/video-generators")
    ids = {p["provider_id"] for p in r.json()}
    assert ids == set(_GPU_PLACEHOLDERS) | set(_NON_GPU_VIDEO)


# ---------------------------------------------------------------------------
# /api/v1/video/generate stays metadata-only for every GPU provider
# ---------------------------------------------------------------------------


def _make_wav() -> bytes:
    import io
    import wave

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
    iend = b"IEND"
    iend_chunk = struct.pack(">I", 0) + iend + struct.pack(
        ">I", zlib.crc32(iend) & 0xFFFFFFFF
    )
    return sig + ihdr_chunk + idat_chunk + iend_chunk


async def _create_job_with_inputs(client: AsyncClient) -> tuple[str, str, str]:
    create = await client.post(
        "/api/v1/jobs",
        json={
            "brief": "phase 7a planning",
            "synthetic_person_confirmed": True,
            "consent_confirmed": True,
            "target_duration_seconds": 30,
            "watermark_required": True,
            "c2pa_required": True,
            "script_text": "phase 7a",
        },
    )
    assert create.status_code == 201, create.text
    job_id = create.json()["id"]

    img = await client.post(
        "/api/v1/uploads/image",
        files={"file": ("face.png", _make_png(), "image/png")},
    )
    assert img.status_code == 201, img.text
    img_artifact_id = img.json()["artifact_id"]

    aud = await client.post(
        "/api/v1/uploads/audio",
        files={"file": ("voice.wav", _make_wav(), "audio/wav")},
    )
    assert aud.status_code == 201, aud.text
    aud_artifact_id = aud.json()["artifact_id"]

    return job_id, img_artifact_id, aud_artifact_id


@pytest.mark.parametrize("provider_id", _GPU_PLACEHOLDERS[:3])  # liveportrait → unknown
async def test_video_generate_stays_not_implemented_for_gpu_placeholders(
    app_under_test, provider_id
):
    job_id, img_id, aud_id = await _create_job_with_inputs(app_under_test)
    r = await app_under_test.post(
        "/api/v1/video/generate",
        json={
            "job_id": job_id,
            "image_artifact_id": img_id,
            "audio_artifact_id": aud_id,
            "provider_id": provider_id,
            "target_duration_seconds": 30,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "not_implemented", body
    assert body["error_code"] == "provider_not_implemented"
    assert body["output_video_artifact_id"] is None, (
        "no MP4 may be produced in Phase 7A — planning only"
    )
    # The body must echo the request shape, but it must NOT carry any binary
    # payload, base64 blob, or download URL.
    flat = json.dumps(body).lower()
    for forbidden in ("base64", "data:video", ".mp4", "ffmpeg", "video_bytes"):
        assert forbidden not in flat, (
            f"video/generate body leaked {forbidden!r} — implies real output"
        )


async def test_video_generate_rejects_liveportrait_until_explicitly_wired(
    app_under_test,
):
    """LivePortrait is in the *catalog* (so operators see it) but the
    generate endpoint refuses it — it has not been promoted to a runnable
    placeholder. The 6A endpoint's known set is {sadtalker, musetalk,
    wav2lip}; liveportrait must come back as not_configured / unknown
    provider, never as a quietly-implemented path."""
    job_id, img_id, aud_id = await _create_job_with_inputs(app_under_test)
    r = await app_under_test.post(
        "/api/v1/video/generate",
        json={
            "job_id": job_id,
            "image_artifact_id": img_id,
            "audio_artifact_id": aud_id,
            "provider_id": "liveportrait",
            "target_duration_seconds": 30,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "not_configured"
    assert body["error_code"] == "unknown_provider"


# ---------------------------------------------------------------------------
# Docker compose invariants
# ---------------------------------------------------------------------------


def _compose_services(*compose_files: Path, profiles: list[str] | None = None) -> set[str]:
    cmd = ["docker", "compose"]
    for f in compose_files:
        cmd.extend(["-f", str(f)])
    for p in profiles or []:
        cmd.extend(["--profile", p])
    cmd.extend(["config", "--services"])
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if res.returncode != 0:
        pytest.skip(
            f"docker compose unavailable or failed (rc={res.returncode}): "
            f"{res.stderr.strip()}"
        )
    return {ln.strip() for ln in res.stdout.splitlines() if ln.strip()}


def test_docker_light_default_excludes_cuda_agents():
    """Without --profile gpu, no CUDA agent is part of the dev stack."""
    if not COMPOSE_DEV.exists():  # pragma: no cover
        pytest.skip("compose.dev.yml not present")
    services = _compose_services(COMPOSE_DEV)
    for cuda in _CUDA_AGENTS:
        assert cuda not in services, (
            f"{cuda} appears in the default light stack — "
            "GPU agents must stay behind --profile gpu"
        )


def test_docker_gpu_overlay_attaches_to_cuda_agents():
    """compose.gpu.yml has a `<<: *gpu-one` reservation for each CUDA agent."""
    text = COMPOSE_GPU.read_text()
    for cuda in _CUDA_AGENTS:
        # Look for the service header followed (within a small window) by
        # the *gpu-one anchor merge. Plain substring is enough — the file
        # is small and deterministic.
        m = re.search(
            rf"^\s*{re.escape(cuda)}:\s*\n(?:.*\n){{0,3}}\s*<<:\s*\*gpu-one",
            text,
            re.MULTILINE,
        )
        assert m is not None, f"{cuda} is missing the *gpu-one merge in compose.gpu.yml"


def test_docker_gpu_overlay_filters_cuda_agents_without_profile():
    """`-f dev -f gpu` without --profile gpu must still hide CUDA agents."""
    if not COMPOSE_DEV.exists():  # pragma: no cover
        pytest.skip("compose files not present")
    services = _compose_services(COMPOSE_DEV, COMPOSE_GPU)
    for cuda in _CUDA_AGENTS:
        assert cuda not in services, (
            f"{cuda} surfaced from the GPU overlay without --profile gpu — "
            "overlay must remain additive only when the profile is on"
        )


def test_docker_gpu_overlay_exposes_cuda_agents_with_profile():
    if not COMPOSE_DEV.exists():  # pragma: no cover
        pytest.skip("compose files not present")
    services = _compose_services(COMPOSE_DEV, COMPOSE_GPU, profiles=["gpu"])
    for cuda in _CUDA_AGENTS:
        assert cuda in services, (
            f"{cuda} must surface under --profile gpu so operators can opt-in"
        )


# ---------------------------------------------------------------------------
# Dockerfile.cuda is still a Phase 0 stub (no torch install)
# ---------------------------------------------------------------------------


def test_dockerfile_cuda_stays_within_phase7c_envelope():
    """Phase 7C hardened Dockerfile.cuda beyond a Phase 0 stub but kept
    every heavy install gated. The invariant now is:

    - torch may install **only** inside an ``INSTALL_TORCH`` build-arg
      branch (default false).
    - SadTalker / MuseTalk / Wav2Lip / diffusers / xformers /
      transformers / GFPGAN deps must not install at all yet
      (Phase 7D's job).
    - No model weight downloads (``wget`` / ``huggingface-cli``).
    - Base image stays a CUDA runtime.
    """
    text = DOCKERFILE_CUDA.read_text()
    lowered = text.lower()

    active_only = "\n".join(
        ln for ln in text.splitlines() if not ln.lstrip().startswith("#")
    )
    active_lower = active_only.lower()

    # 1. No SadTalker / heavy-stack installs anywhere — gated or not.
    fully_forbidden = [
        "pip install diffusers",
        "pip install xformers",
        "pip install transformers",
        "pip install sadtalker",
        "pip install musetalk",
        "pip install wav2lip",
        "pip install gfpgan",
        "pip install accelerate",
        "wget ",
        "huggingface-cli download",
        "hf_hub_download",
    ]
    for needle in fully_forbidden:
        assert needle.lower() not in active_lower, (
            f"Dockerfile.cuda has an active line containing {needle!r}; "
            "Phase 7C still defers all SadTalker / heavy-ML deps + "
            "all model downloads to Phase 7D."
        )

    # 2. If torch installs at all, it must be inside the
    # ``$INSTALL_TORCH`` opt-in gate. The simplest way to check that:
    # every line containing the literal ``torch==`` (the install pin)
    # must live inside a block guarded by ``"$INSTALL_TORCH"``.
    torch_install_lines = [
        i for i, ln in enumerate(active_only.splitlines()) if "torch==" in ln.lower()
    ]
    if torch_install_lines:
        gate_blocks: list[tuple[int, int]] = []
        depth = 0
        block_start = -1
        for i, ln in enumerate(active_only.splitlines()):
            low = ln.lower()
            if "install_torch" in low and 'if [ "$install_torch"' in low:
                block_start = i
                depth += 1
            elif depth and (low.strip() == "fi" or low.strip().startswith("fi ")):
                gate_blocks.append((block_start, i))
                depth -= 1
                block_start = -1
        for line_idx in torch_install_lines:
            assert any(start <= line_idx <= end for start, end in gate_blocks), (
                f"Dockerfile.cuda line {line_idx} installs torch outside the "
                "$INSTALL_TORCH opt-in gate."
            )

    # 3. CUDA base unchanged.
    assert "nvidia/cuda" in lowered, "Dockerfile.cuda base image drifted"


# ---------------------------------------------------------------------------
# Backend & agents wheel hygiene — no torch / diffusers in dep manifests
# ---------------------------------------------------------------------------


_FORBIDDEN_DEPS = (
    "torch",
    "torchvision",
    "torchaudio",
    "diffusers",
    "xformers",
    "transformers",
    "accelerate",
    "bitsandbytes",
    "sadtalker",
    "musetalk",
    "wav2lip",
    "liveportrait",
)


_DEP_TABLE_RE = re.compile(
    r"^dependencies\s*=\s*\[(.*?)^\]",
    re.MULTILINE | re.DOTALL,
)
_OPT_TABLE_RE = re.compile(
    r"^\[project\.optional-dependencies\]\s*\n(.*?)(?=^\[|\Z)",
    re.MULTILINE | re.DOTALL,
)


def _dep_tables_text(pyproject: Path) -> str:
    """Concatenate the project's actual dependency tables.

    We only care about ``dependencies`` and ``[project.optional-dependencies]``
    — sub-package paths like ``"agents.lipsync.providers.sadtalker"`` in
    ``[tool.setuptools]`` are package layout, not deps, and must not be
    treated as forbidden imports.
    """
    raw = pyproject.read_text()
    # Strip comment-only lines first so commented examples don't trip the test.
    decommented = "\n".join(
        ln for ln in raw.splitlines() if not ln.lstrip().startswith("#")
    )
    parts: list[str] = []
    m = _DEP_TABLE_RE.search(decommented)
    if m:
        parts.append(m.group(1))
    m2 = _OPT_TABLE_RE.search(decommented)
    if m2:
        parts.append(m2.group(1))
    return "\n".join(parts)


def test_backend_pyproject_has_no_gpu_deps():
    text = _dep_tables_text(BACKEND_PYPROJECT)
    for needle in _FORBIDDEN_DEPS:
        pattern = re.compile(rf'(?<![\w-]){re.escape(needle)}(?![\w-])')
        assert not pattern.search(text), (
            f"backend/pyproject.toml depends on {needle!r}; "
            "GPU/model deps must stay out of the default backend wheel."
        )


def test_agents_pyproject_has_no_gpu_deps():
    text = _dep_tables_text(AGENTS_PYPROJECT)
    for needle in _FORBIDDEN_DEPS:
        pattern = re.compile(rf'(?<![\w-]){re.escape(needle)}(?![\w-])')
        assert not pattern.search(text), (
            f"agents/pyproject.toml base install depends on {needle!r}; "
            "GPU/model deps belong in GPU-only image installs only."
        )


# ---------------------------------------------------------------------------
# Live import audit — `import app.main` and the registry must not pull torch
# ---------------------------------------------------------------------------


_FORBIDDEN_RUNTIME_IMPORTS = (
    "torch",
    "torchvision",
    "torchaudio",
    "diffusers",
    "xformers",
    "transformers",
    "accelerate",
    "sadtalker",
    "musetalk",
    "wav2lip",
    "liveportrait",
)


def test_backend_app_import_does_not_load_torch_or_diffusers():
    """Subprocess-isolated: importing the FastAPI app must not transitively
    load any GPU/model dep. If it does, something is leaking heavy code
    into the default backend container."""
    code = (
        "import sys\n"
        "import app.main  # noqa: F401\n"
        f"leaked = [m for m in {_FORBIDDEN_RUNTIME_IMPORTS!r} if m in sys.modules]\n"
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
        f"backend app import transitively loaded {leaked!r}; "
        "this would force torch/diffusers into the default backend image."
    )


def test_provider_registry_import_does_not_load_torch_or_diffusers():
    code = (
        "import sys\n"
        "import app.services.provider_registry  # noqa: F401\n"
        f"leaked = [m for m in {_FORBIDDEN_RUNTIME_IMPORTS!r} if m in sys.modules]\n"
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
        f"provider_registry loaded {leaked!r}; the catalog must be metadata-only."
    )
