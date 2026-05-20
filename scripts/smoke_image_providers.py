#!/usr/bin/env python3
"""Smoke: image-provider registry + health — Phase IG-6.

Checks the provider registry loads, the identity providers + Kontext stub
are present, and prints each provider's health. No GPU needed; ComfyUI
health is "not_configured" until COMFYUI_BASE_URL is wired + reachable.

Run:  python scripts/smoke_image_providers.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.image_providers import get_image_provider  # noqa: E402
from app.services.image_providers.dispatch import available_provider_ids  # noqa: E402
from app.services.image_workflow_select import (  # noqa: E402
    detect_total_vram_gb,
    select_workflow,
)


async def main() -> int:
    ids = available_provider_ids()
    print("Registered image providers:", ", ".join(sorted(ids)))
    assert "comfyui_local" in ids, "comfyui_local must be registered"
    assert "flux_kontext" in ids, "flux_kontext stub must be registered"

    print(f"\nDetected VRAM: {detect_total_vram_gb()} GB")
    for mode in ("initial", "consistent"):
        sel = select_workflow(mode)
        print(f"  {mode:11s} → {sel.workflow_name} [{sel.tier}] ({sel.reason})")

    print("\nProvider health:")
    for pid in sorted(ids):
        try:
            h = await get_image_provider(pid).health_check()
            print(f"  {pid:24s} {h.status:16s} {h.notes[:60]}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {pid:24s} ERROR {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
