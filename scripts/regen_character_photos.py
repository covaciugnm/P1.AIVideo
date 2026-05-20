#!/usr/bin/env python3
"""Regenerate + VALIDATE character photos via the API (security-aware).

For each active character:
  1. delete current generated variations (status draft/accepted that are NOT
     the canonical face/full-body reference — those are kept; InstantID needs them),
  2. generate 1 full-body + 2 upper-body identity-consistent photos,
  3. VALIDATE each: GET /content must return 200 + a real PNG (>50 KB).

Stdlib only (urllib). Usage:
  P1_TOKEN=<super-admin token> python scripts/regen_character_photos.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

BASE = os.environ.get("P1_BASE", "http://localhost:8001")
TOKEN = os.environ["P1_TOKEN"]
AUTH = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

CONTEXTS = [
    {"label": "corp complet", "scene_prompt": "standing in a professional photography studio, full length",
     "outfit_prompt": "elegant smart outfit", "framing": "full body", "mood": "confident"},
    {"label": "bust 1", "scene_prompt": "upper body portrait, soft daylight, plain background",
     "outfit_prompt": "smart blazer", "framing": "upper body, medium close-up", "mood": "warm"},
    {"label": "bust 2", "scene_prompt": "upper body portrait outdoors, autumn city background, bokeh",
     "outfit_prompt": "casual coat", "framing": "upper body, head and shoulders", "season": "autumn", "mood": "relaxed"},
]


def _req(method, path, body=None, expect_json=True):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=AUTH, method=method)
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if expect_json and raw else raw)
    except urllib.error.HTTPError as e:
        return e.code, (json.loads(e.read() or b"{}") if expect_json else b"")


def _validate(cid, image_id):
    req = urllib.request.Request(
        f"{BASE}/api/v1/characters/{cid}/images/{image_id}/content",
        headers={"Authorization": f"Bearer {TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            blob = r.read()
            ok = r.status == 200 and blob[:8] == b"\x89PNG\r\n\x1a\n" and len(blob) > 50_000
            return ok, len(blob)
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def main() -> int:
    _, chars = _req("GET", "/api/v1/characters")
    chars = [c for c in chars["items"] if c.get("status") in ("active", "editing")]
    for c in chars:
        cid, name = c["id"], c["name"]
        face, body = c.get("main_reference_image_id"), c.get("full_body_reference_image_id")
        print(f"\n=== {name} ({cid[:8]}) face={bool(face)} body={bool(body)} ===")
        if not face or not body:
            print("  ! missing canonical refs — skipping (cannot run InstantID).")
            continue
        # 1) delete current non-reference images
        _, imgs = _req("GET", f"/api/v1/characters/{cid}/images")
        for im in imgs["items"]:
            if im["id"] in (face, body):
                continue
            st, _ = _req("DELETE", f"/api/v1/characters/{cid}/images/{im['id']}", expect_json=False)
            print(f"  deleted old {im['id'][:8]} [{st}]")
        # 2) generate + 3) validate
        for ctx in CONTEXTS:
            body_req = {k: v for k, v in ctx.items() if k != "label"}
            body_req.update({"aspect_ratio": "portrait", "quality_preset": "standard"})
            st, resp = _req("POST", f"/api/v1/characters/{cid}/images/generate-consistent", body_req)
            if st != 200 or "id" not in resp:
                print(f"  ✗ {ctx['label']}: gen failed [{st}] {str(resp)[:160]}")
                continue
            ok, sz = _validate(cid, resp["id"])
            print(f"  {'✓' if ok else '✗ INVALID'} {ctx['label']} → {resp['id'][:8]} validated={ok} bytes={sz}")
            time.sleep(1)
    print("\nREGEN_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
