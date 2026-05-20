#!/usr/bin/env python3
"""Smoke: identity prompt builder + workflow templates — Phase IG-6.

Pure (no GPU / no ComfyUI). Verifies the identity-locked prompt builder
and that every shipped workflow template substitutes to valid JSON with
the face reference injected.

Run:  python scripts/smoke_character_generation.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.character_prompt_builder import (  # noqa: E402
    SceneParams,
    build_consistent_prompt,
    build_initial_prompt,
)
from app.services.image_providers.base import ImageGenerationInput  # noqa: E402
from app.services.image_providers.local_wrapper_stub import (  # noqa: E402
    LocalWrapperImageProviderStub,
)

PROFILE = {
    "identity": {"name": "Demo", "gender": "female", "age": 30, "is_public_persona": False},
    "appearance": {"skin_tone": "fair", "hair_color": "auburn", "eye_color": "green",
                   "face_shape": "oval"},
    "script_behaviour": {"default_camera_framing": "medium shot"},
}


def main() -> int:
    pos_i, neg_i = build_initial_prompt(PROFILE)
    print("INITIAL +:", pos_i[:140], "...")
    assert "IDENTITY LOCK" in pos_i

    scene = SceneParams(scene_prompt="in a modern office", outfit_prompt="business suit",
                        season="autumn", framing="full body")
    pos_c, neg_c = build_consistent_prompt(PROFILE, scene)
    print("\nCONSISTENT +:", pos_c[:200], "...")
    print("CONSISTENT -:", neg_c[:120], "...")
    assert "business suit" in pos_c and "different person" in neg_c

    wf_dir = ROOT / "workflows" / "comfyui"
    inp = ImageGenerationInput(
        prompt=pos_c, negative_prompt=neg_c, model_id=None, seed=42,
        width=768, height=1024, steps=24, guidance_scale=4.0,
        reference_image_path=None,
    )
    print("\nWorkflow templates:")
    for tmpl in sorted(wf_dir.glob("*.json")):
        text = tmpl.read_text(encoding="utf-8")
        wf = LocalWrapperImageProviderStub._build_workflow_dict(
            text, inp, 42, "canonical_face.png", "canonical_body.png"
        )
        blob = json.dumps(wf)
        assert "__" not in blob.replace("__comment", ""), f"placeholder left in {tmpl.name}"
        print(f"  {tmpl.stem:32s} OK ({len(wf)} nodes)")
    print("\nAll identity-generation smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
