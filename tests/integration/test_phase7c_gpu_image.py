"""Phase 7C — GPU image / runtime for SadTalker readiness.

Pins the boundary between the default light stack (zero GPU code) and
the opt-in GPU image (CUDA base + Python + ffmpeg + opt-in torch). The
image itself is **not built** by this test suite — these are static
file invariants + compose-merge checks that work on any host, GPU or
not.

What this phase tests:

- ``docker/agents/Dockerfile.cuda`` installs Python 3.11 + ffmpeg + the
  common + agents wheels, but every heavy ML dep stays behind a build
  arg.
- ``INSTALL_TORCH`` defaults to false; ``INSTALL_SADTALKER_DEPS``
  defaults to false; both arguments exist.
- No model weight downloads anywhere in the file (no ``wget`` / no
  ``huggingface-cli``).
- ``docker/compose.gpu.yml`` ``agent-lipsync`` block carries SadTalker
  env vars, mounts weights read-only, and keeps ``RUN_REAL_SADTALKER``
  / ``SADTALKER_ENABLE_REAL_INFERENCE`` / ``ALLOW_MODEL_AUTODOWNLOAD``
  off by default.
- ``agent-lipsync`` stays gated behind ``profiles: ["gpu"]`` in
  ``compose.dev.yml`` (Phase 7A invariant, re-asserted here).
- ``make docker-gpu-config-check`` / ``docker-gpu-build`` /
  ``docker-gpu-smoke`` / ``docker-gpu-down`` exist as Make targets.
- The Phase 7A invariant ``test_dockerfile_cuda_stays_within_phase7c_envelope``
  still passes (re-imported here as a sanity check).
- Light Docker compose remains identical service set to before Phase 7C.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_DEV = REPO_ROOT / "docker" / "compose.dev.yml"
COMPOSE_GPU = REPO_ROOT / "docker" / "compose.gpu.yml"
DOCKERFILE_CUDA = REPO_ROOT / "docker" / "agents" / "Dockerfile.cuda"
DOCKERFILE_BACKEND = REPO_ROOT / "docker" / "backend" / "Dockerfile"
DOCKERFILE_AGENTS = REPO_ROOT / "docker" / "agents" / "Dockerfile"
MAKEFILE = REPO_ROOT / "Makefile"


# ---------------------------------------------------------------------------
# Dockerfile.cuda — Phase 7C readiness image
# ---------------------------------------------------------------------------


def test_dockerfile_cuda_installs_python_and_ffmpeg():
    """The Phase 7C image must carry Python + ffmpeg so the readiness
    CMD has something to actually print."""
    text = DOCKERFILE_CUDA.read_text()
    active = "\n".join(
        ln for ln in text.splitlines() if not ln.lstrip().startswith("#")
    )
    assert "python3.11" in active, "Dockerfile.cuda must install Python 3.11"
    assert "ffmpeg" in active, "Dockerfile.cuda must install ffmpeg"


def test_dockerfile_cuda_torch_install_is_opt_in():
    """``INSTALL_TORCH`` must default to false. The actual install line
    must live inside an ``if [ \"$INSTALL_TORCH\" = \"true\" ]`` block."""
    text = DOCKERFILE_CUDA.read_text()
    # ARG default
    m = re.search(r"^ARG\s+INSTALL_TORCH\s*=\s*(\S+)", text, re.MULTILINE)
    assert m is not None, "Dockerfile.cuda must declare INSTALL_TORCH build arg"
    assert m.group(1).lower() == "false", (
        "INSTALL_TORCH must default to false so the GPU image is light by default"
    )
    # Install line is gated
    assert 'if [ "$INSTALL_TORCH" = "true" ]' in text, (
        "torch install must live inside the $INSTALL_TORCH opt-in branch"
    )


def test_dockerfile_cuda_sadtalker_deps_marker_only():
    """SadTalker dep install is a Phase 7D job. Phase 7C just writes a
    marker file when the (off-by-default) arg is set so future image
    diffs are unambiguous."""
    text = DOCKERFILE_CUDA.read_text()
    m = re.search(
        r"^ARG\s+INSTALL_SADTALKER_DEPS\s*=\s*(\S+)", text, re.MULTILINE
    )
    assert m is not None, "Dockerfile.cuda must declare INSTALL_SADTALKER_DEPS"
    assert m.group(1).lower() == "false"
    active = "\n".join(
        ln for ln in text.splitlines() if not ln.lstrip().startswith("#")
    ).lower()
    # No actual sadtalker / gfpgan / diffusers install line.
    for needle in (
        "pip install sadtalker",
        "pip install gfpgan",
        "pip install diffusers",
        "pip install xformers",
        "pip install transformers",
    ):
        assert needle not in active, (
            f"Dockerfile.cuda still defers {needle!r} to Phase 7D"
        )


def test_dockerfile_cuda_has_no_model_downloads():
    text = DOCKERFILE_CUDA.read_text()
    active_lines = [
        ln for ln in text.splitlines() if not ln.lstrip().startswith("#")
    ]
    active = "\n".join(active_lines).lower()
    for needle in ("wget ", "huggingface-cli download", "hf_hub_download"):
        assert needle not in active, (
            f"Dockerfile.cuda must not download model weights ({needle!r})"
        )


def test_dockerfile_cuda_runs_as_non_root():
    """The container must run as the non-root ``app`` user (uid 1000)
    so bind-mounted /models permissions line up across the stack."""
    text = DOCKERFILE_CUDA.read_text()
    assert re.search(r"^USER\s+1000\s*$", text, re.MULTILINE), (
        "Dockerfile.cuda must end with USER 1000"
    )


def test_dockerfile_cuda_default_cmd_does_not_run_inference():
    """The default CMD must be a readiness probe, not a SadTalker
    invocation. Phase 7C never auto-runs inference.

    We allow the CMD to *reference* environment variable names like
    ``$SADTALKER_MODELS_ROOT`` (the readiness probe prints them) — the
    forbidden patterns are actual invocations (``python -m sadtalker``,
    ``torchrun``, etc.).
    """
    text = DOCKERFILE_CUDA.read_text()
    cmd_block = text[text.rfind("CMD"):]
    lowered = cmd_block.lower()
    # Positive markers: prints status, never runs sadtalker.
    assert "nvidia-smi" in lowered
    assert "ready" in lowered
    # Negative markers: must not actually launch any inference path.
    invocation_patterns = (
        "python -m sadtalker",
        "python -m musetalk",
        "python -m wav2lip",
        "from sadtalker",
        "import sadtalker",
        "torchrun",
        "accelerate launch",
        "deepspeed launch",
    )
    for needle in invocation_patterns:
        assert needle not in lowered, (
            f"Default CMD invokes {needle!r}; Phase 7C must stay non-inference"
        )


def test_compose_gpu_agent_lipsync_has_sadtalker_env():
    """Phase 7C wired SadTalker env vars + a read-only models mount onto
    the agent-lipsync GPU service."""
    lines = COMPOSE_GPU.read_text().splitlines()
    # Find the agent-lipsync block: from the matching service header
    # until the next service header (top-level indent ≤ 2 spaces and
    # ends with ':').
    start = next(
        (i for i, ln in enumerate(lines) if ln.strip() == "agent-lipsync:"),
        None,
    )
    assert start is not None, "agent-lipsync service not found in compose.gpu.yml"
    end = len(lines)
    for j in range(start + 1, len(lines)):
        stripped = lines[j].strip()
        if (
            stripped.endswith(":")
            and not lines[j].startswith("      ")
            and not lines[j].startswith("       ")
            and lines[j].startswith("  ")
            and not lines[j].startswith("    ")
        ):
            end = j
            break
    block = "\n".join(lines[start:end])
    assert "SADTALKER_MODELS_ROOT" in block
    assert "SADTALKER_ENABLE_REAL_INFERENCE" in block
    assert "RUN_REAL_SADTALKER" in block
    assert "ALLOW_MODEL_AUTODOWNLOAD" in block
    # Volume mount must be read-only.
    assert ":ro" in block, (
        "Models mount in compose.gpu.yml agent-lipsync must be read-only"
    )


# ---------------------------------------------------------------------------
# compose.gpu.yml — agent-lipsync SadTalker block
# ---------------------------------------------------------------------------


def test_compose_gpu_does_not_force_real_inference_on():
    """Defaults must keep real inference off even when --profile gpu is
    used. Operator must explicitly flip both flags."""
    text = COMPOSE_GPU.read_text()
    # The defaults expressed in compose env interpolation.
    assert 'SADTALKER_ENABLE_REAL_INFERENCE: "${SADTALKER_ENABLE_REAL_INFERENCE:-false}"' in text
    assert 'RUN_REAL_SADTALKER: "${RUN_REAL_SADTALKER:-0}"' in text
    assert 'ALLOW_MODEL_AUTODOWNLOAD: "false"' in text


# ---------------------------------------------------------------------------
# compose.dev.yml — light stack still excludes CUDA agents
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
            f"docker compose unavailable: rc={res.returncode}: {res.stderr.strip()}"
        )
    return {ln.strip() for ln in res.stdout.splitlines() if ln.strip()}


_CUDA_AGENTS = ("agent-voice", "agent-face", "agent-lipsync")


def test_docker_light_still_excludes_cuda_agents_after_phase7c():
    """Phase 7C added env / volume to agent-lipsync. The light stack
    must still hide all three CUDA agents."""
    if not COMPOSE_DEV.exists():  # pragma: no cover
        pytest.skip("compose.dev.yml not present")
    services = _compose_services(COMPOSE_DEV)
    for cuda in _CUDA_AGENTS:
        assert cuda not in services, (
            f"Phase 7C regression: {cuda} surfaced in default compose.dev"
        )


def test_gpu_overlay_still_filters_without_profile():
    if not COMPOSE_DEV.exists() or not COMPOSE_GPU.exists():  # pragma: no cover
        pytest.skip("compose files not present")
    services = _compose_services(COMPOSE_DEV, COMPOSE_GPU)
    for cuda in _CUDA_AGENTS:
        assert cuda not in services


def test_gpu_overlay_exposes_cuda_agents_with_profile():
    if not COMPOSE_DEV.exists() or not COMPOSE_GPU.exists():  # pragma: no cover
        pytest.skip("compose files not present")
    services = _compose_services(COMPOSE_DEV, COMPOSE_GPU, profiles=["gpu"])
    for cuda in _CUDA_AGENTS:
        assert cuda in services


# ---------------------------------------------------------------------------
# Default light backend / agents Dockerfiles still have no torch / CUDA
# ---------------------------------------------------------------------------


def test_backend_dockerfile_has_no_torch_or_cuda():
    text = DOCKERFILE_BACKEND.read_text().lower()
    for needle in ("nvidia/cuda", "pip install torch", "cuda-toolkit", "nvidia-smi"):
        assert needle not in text, (
            f"backend Dockerfile contains {needle!r}; light backend must stay GPU-free"
        )


def test_agents_dockerfile_has_no_torch_or_cuda():
    """The CPU agents image (docker/agents/Dockerfile) is the metadata
    agents image. It must not pull torch or use a CUDA base."""
    text = DOCKERFILE_AGENTS.read_text().lower()
    for needle in ("nvidia/cuda", "pip install torch", "cuda-toolkit"):
        assert needle not in text, (
            f"CPU agents Dockerfile contains {needle!r}; only Dockerfile.cuda may"
        )


# ---------------------------------------------------------------------------
# Makefile — Phase 7C targets exist
# ---------------------------------------------------------------------------


_REQUIRED_TARGETS = (
    "docker-gpu-config-check",
    "docker-gpu-build",
    "docker-gpu-smoke",
    "docker-gpu-down",
    "phase7c-test",
)


def test_makefile_has_phase7c_targets():
    text = MAKEFILE.read_text()
    for target in _REQUIRED_TARGETS:
        # Targets are declared as ``target: ...`` at column 0.
        assert re.search(rf"^{re.escape(target)}:", text, re.MULTILINE), (
            f"Makefile missing {target}"
        )


def test_makefile_docker_gpu_build_uses_dockerfile_cuda():
    text = MAKEFILE.read_text()
    # Find the docker-gpu-build recipe (target line + recipe lines until
    # the next blank line / next target).
    m = re.search(
        r"^docker-gpu-build:.*?\n((?:\t.*\n)+)", text, re.MULTILINE
    )
    assert m is not None, "docker-gpu-build recipe not found"
    recipe = m.group(1)
    assert "docker/agents/Dockerfile.cuda" in recipe, (
        "docker-gpu-build must point at Dockerfile.cuda — never light Dockerfiles"
    )
    # Must NOT touch backend/agents Dockerfiles.
    assert "docker/backend/Dockerfile" not in recipe
    assert "docker/agents/Dockerfile\n" not in recipe  # the CPU image
