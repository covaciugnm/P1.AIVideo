#!/usr/bin/env python3
"""Generate 4 identity-consistent seasonal variations per character.

For every active character it:
  1. ensures a canonical FACE reference (skips if already set),
  2. ensures a canonical FULL-BODY reference — if missing, generates an
     initial full-body candidate and promotes it,
  3. generates 4 identity-consistent variations (one per season) with
     diversified scene + outfit + framing.

Uses ONLY the new identity pipeline (generate-initial / generate-consistent).
Requires the ComfyUI runtime + identity model weights to be installed and
``model-comfyui`` reachable — otherwise the calls return a categorised
``provider_not_configured`` / connection error (no fake output).

Run:  python scripts/generate_seasonal_variations.py [--base http://localhost:8001]
"""
from __future__ import annotations

import argparse
import sys
import time

import requests

# season → diversified (scene, outfit, framing, mood) so the 4 images differ.
SEASONS = [
    {
        "season": "spring",
        "scene_prompt": "walking through a blooming park, cherry blossoms",
        "outfit_prompt": "light pastel trench coat and a scarf",
        "framing": "full body, three-quarter angle",
        "mood": "fresh and optimistic",
    },
    {
        "season": "summer",
        "scene_prompt": "on a sunlit seaside promenade, bright daylight",
        "outfit_prompt": "linen summer outfit, sunglasses",
        "framing": "medium full shot",
        "mood": "relaxed",
    },
    {
        "season": "autumn",
        "scene_prompt": "a city street with golden falling leaves, soft overcast light",
        "outfit_prompt": "wool coat, knitted sweater, ankle boots",
        "framing": "full body, side three-quarter",
        "mood": "calm and thoughtful",
    },
    {
        "season": "winter",
        "scene_prompt": "a snowy old-town square at dusk, warm street lights",
        "outfit_prompt": "heavy padded winter jacket, gloves and a beanie",
        "framing": "full body, frontal",
        "mood": "cozy",
    },
]


def _get(base, path):
    r = requests.get(base + path, timeout=30)
    r.raise_for_status()
    return r.json()


def _post(base, path, json_body):
    r = requests.post(base + path, json=json_body, timeout=900)
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8001")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    chars = _get(base, "/api/v1/characters")["items"]
    chars = [c for c in chars if c.get("status") in ("active", "editing")]
    print(f"{len(chars)} characters to process.\n")

    for c in chars:
        cid, name = c["id"], c["name"]
        print(f"=== {name} ({cid[:8]}) ===")
        if not c.get("main_reference_image_id"):
            print("  ! no canonical face — generate + promote a face first; skipping.")
            continue

        # Ensure a canonical full-body reference.
        if not c.get("full_body_reference_image_id"):
            print("  • generating an initial full-body candidate…")
            r = _post(base, f"/api/v1/characters/{cid}/images/generate-initial",
                      {"aspect_ratio": "portrait", "quality_preset": "standard"})
            if r.status_code != 200:
                print(f"    ✗ generate-initial failed [{r.status_code}]: {r.text[:200]}")
                continue
            img_id = r.json()["id"]
            pr = _post(base, f"/api/v1/characters/{cid}/images/{img_id}/set-full-body-reference", {})
            if pr.status_code != 200:
                print(f"    ✗ set-full-body-reference failed: {pr.text[:160]}")
                continue
            print("    ✓ full-body reference set")

        # 4 seasonal consistent variations.
        for s in SEASONS:
            body = {
                "scene_prompt": s["scene_prompt"], "outfit_prompt": s["outfit_prompt"],
                "season": s["season"], "framing": s["framing"], "mood": s["mood"],
                "aspect_ratio": "portrait", "quality_preset": "standard",
            }
            r = _post(base, f"/api/v1/characters/{cid}/images/generate-consistent", body)
            if r.status_code == 200:
                print(f"    ✓ {s['season']:7s} → {r.json()['id'][:8]}")
            else:
                print(f"    ✗ {s['season']:7s} [{r.status_code}]: {r.text[:160]}")
            time.sleep(1)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
