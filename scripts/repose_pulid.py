#!/usr/bin/env python3
"""Re-pose all characters with the PuLID-FLUX engine.

Per character: KEEP photo 1 (face reference, the PuLID identity anchor),
generate photo 2 = full body + photos 3-5 = varied poses, promote the new
full-body as the full-body reference, delete the old non-face photos, and
VALIDATE every new file (real PNG via /content). Stdlib only.

  P1_TOKEN=<super-admin token> python scripts/repose_pulid.py
"""
from __future__ import annotations
import json, os, sys, time, urllib.request, urllib.error

BASE = os.environ.get("P1_BASE", "http://localhost:8001")
TOKEN = os.environ["P1_TOKEN"]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

POSES = [
    {"label": "corp întreg", "scene_prompt": "full length studio portrait, standing, neutral seamless background",
     "outfit_prompt": "elegant smart outfit", "framing": "full body", "mood": "confident"},
    {"label": "ipostază birou", "scene_prompt": "sitting at a desk in a bright modern office, three-quarter view",
     "outfit_prompt": "smart casual blazer", "framing": "medium full shot", "mood": "calm"},
    {"label": "ipostază stradă", "scene_prompt": "walking on a european city street, candid, soft daylight",
     "outfit_prompt": "casual coat", "framing": "three-quarter shot", "season": "autumn", "mood": "relaxed"},
    {"label": "ipostază portret", "scene_prompt": "relaxed portrait leaning against a wall, warm indoor light",
     "outfit_prompt": "casual outfit", "framing": "upper body, medium close-up", "mood": "warm"},
]


def req(method, path, body=None, want_json=True):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, headers=H, method=method)
    try:
        with urllib.request.urlopen(r, timeout=900) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if want_json and raw else raw)
    except urllib.error.HTTPError as e:
        return e.code, (json.loads(e.read() or b"{}") if want_json else b"")


def validate(cid, iid):
    r = urllib.request.Request(f"{BASE}/api/v1/characters/{cid}/images/{iid}/content",
                               headers={"Authorization": f"Bearer {TOKEN}"})
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            b = resp.read()
            return resp.status == 200 and b[:8] == b"\x89PNG\r\n\x1a\n" and len(b) > 50_000, len(b)
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def main() -> int:
    _, chars = req("GET", "/api/v1/characters")
    for c in [c for c in chars["items"] if c.get("status") in ("active", "editing")]:
        cid, name = c["id"], c["name"]
        face = c.get("main_reference_image_id")
        print(f"\n=== {name} ({cid[:8]}) face={bool(face)} ===")
        if not face:
            print("  ! no face reference — skip (PuLID needs the face anchor).")
            continue
        _, before = req("GET", f"/api/v1/characters/{cid}/images")
        old_ids = [i["id"] for i in before["items"] if i["id"] != face]

        new_ids, new_body = [], None
        for p in POSES:
            payload = {k: v for k, v in p.items() if k != "label"}
            payload.update({"aspect_ratio": "portrait", "quality_preset": "standard"})
            st, resp = req("POST", f"/api/v1/characters/{cid}/images/generate-consistent", payload)
            if st != 200 or "id" not in resp:
                print(f"  ✗ {p['label']}: gen failed [{st}] {str(resp)[:160]}")
                continue
            ok, sz = validate(cid, resp["id"])
            print(f"  {'✓' if ok else '✗ INVALID'} {p['label']} → {resp['id'][:8]} bytes={sz}")
            if ok:
                new_ids.append(resp["id"])
                if new_body is None and p["label"] == "corp întreg":
                    new_body = resp["id"]
            time.sleep(1)

        promoted = False
        if new_body:
            st, _ = req("POST", f"/api/v1/characters/{cid}/images/{new_body}/set-full-body-reference")
            promoted = st == 200
            print(f"  full-body reference → {new_body[:8]} [{'set' if promoted else 'NOT set %s'%st}]")

        # delete old non-face photos (keep old full-body only if promotion failed)
        for oid in old_ids:
            if not promoted and oid == c.get("full_body_reference_image_id"):
                print(f"  kept old body {oid[:8]} (new not promoted)")
                continue
            st, _ = req("DELETE", f"/api/v1/characters/{cid}/images/{oid}", want_json=False)
            print(f"  deleted old {oid[:8]} [{st}]")
        print(f"  RESULT: face + {len(new_ids)} PuLID photos")
    print("\nREPOSE_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
