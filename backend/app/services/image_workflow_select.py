"""VRAM-aware ComfyUI workflow + provider selection — Phase IG-2.

Identity-consistent generation always runs on the ``comfyui_local``
provider; what changes is WHICH workflow template (PuLID-FLUX vs
SDXL-InstantID) and that depends on the box's VRAM:

- ``IMAGE_PROVIDER_DEFAULT=auto`` (default): detect total GPU VRAM and
  pick the primary (PuLID-FLUX) on big boxes, the fallback
  (SDXL-InstantID, ~10GB) on <= the threshold (e.g. the 24GB dev box).
- ``IMAGE_PROVIDER_DEFAULT=pulid_flux`` / ``sdxl_instantid``: pin it.

Operators can always override per request (``provider_override`` /
explicit ``workflow``). See workflows/comfyui/README.md.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Big-VRAM cutoff (GB). PuLID-FLUX needs a lot of headroom, especially when
# the box also runs the LLM/lipsync models — see project memory.
_PRIMARY_VRAM_MIN_GB = float(os.environ.get("IMAGE_PRIMARY_VRAM_MIN_GB", "40"))

# Logical preset → (workflow env var name, default workflow stem).
_WORKFLOW_DEFAULTS = {
    "identity_primary": ("IMAGE_IDENTITY_WORKFLOW_PRIMARY", "pulid_flux_consistent"),
    "identity_fallback": ("IMAGE_IDENTITY_WORKFLOW_FALLBACK", "sdxl_instantid_consistent"),
    "initial_primary": ("IMAGE_INITIAL_WORKFLOW_PRIMARY", "pulid_flux_initial"),
    "initial_fallback": ("IMAGE_INITIAL_WORKFLOW_FALLBACK", "sdxl_initial"),
}


@dataclass(frozen=True)
class WorkflowSelection:
    provider_id: str          # always "comfyui_local" for the identity pipeline
    workflow_name: str        # template stem under COMFYUI_WORKFLOW_DIR
    tier: str                 # "primary" | "fallback"
    reason: str               # human-readable why


def _env_workflow(preset: str) -> str:
    env_name, default = _WORKFLOW_DEFAULTS[preset]
    return os.environ.get(env_name, default).strip() or default


def detect_total_vram_gb() -> float | None:
    """Best-effort total VRAM in GB. ``IMAGE_GPU_VRAM_GB_OVERRIDE`` wins
    (useful in tests / headless). Returns None when no GPU is detectable."""
    override = os.environ.get("IMAGE_GPU_VRAM_GB_OVERRIDE", "").strip()
    if override:
        try:
            return float(override)
        except ValueError:
            return None
    smi = shutil.which("nvidia-smi")
    if not smi:
        return None
    try:
        out = subprocess.run(
            [smi, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        # First GPU's total memory in MiB.
        mib = float(out.stdout.strip().splitlines()[0].strip())
        return round(mib / 1024.0, 1)
    except (subprocess.SubprocessError, ValueError, OSError) as exc:
        logger.warning("VRAM detection failed: %s", exc)
        return None


def select_workflow(mode: str) -> WorkflowSelection:
    """Pick the workflow for ``mode`` in {"initial","consistent"}."""
    consistent = mode == "consistent"
    pinned = os.environ.get("IMAGE_PROVIDER_DEFAULT", "auto").strip().lower()

    if pinned in ("pulid_flux", "primary"):
        preset = "identity_primary" if consistent else "initial_primary"
        return WorkflowSelection(
            "comfyui_local", _env_workflow(preset), "primary",
            "pinned IMAGE_PROVIDER_DEFAULT=pulid_flux",
        )
    if pinned in ("sdxl_instantid", "fallback"):
        preset = "identity_fallback" if consistent else "initial_fallback"
        return WorkflowSelection(
            "comfyui_local", _env_workflow(preset), "fallback",
            "pinned IMAGE_PROVIDER_DEFAULT=sdxl_instantid",
        )

    # auto — decide by VRAM.
    vram = detect_total_vram_gb()
    if vram is not None and vram >= _PRIMARY_VRAM_MIN_GB:
        preset = "identity_primary" if consistent else "initial_primary"
        return WorkflowSelection(
            "comfyui_local", _env_workflow(preset), "primary",
            f"auto: {vram}GB VRAM >= {_PRIMARY_VRAM_MIN_GB}GB → PuLID-FLUX",
        )
    preset = "identity_fallback" if consistent else "initial_fallback"
    reason = (
        f"auto: {vram}GB VRAM < {_PRIMARY_VRAM_MIN_GB}GB → SDXL-InstantID"
        if vram is not None
        else "auto: no GPU detected → SDXL-InstantID (safe fallback)"
    )
    return WorkflowSelection("comfyui_local", _env_workflow(preset), "fallback", reason)
