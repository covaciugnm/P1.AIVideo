# 06 — Broken links / buttons / assets

## Buttons / actions with NO backend wiring
- **None that call a missing endpoint.** All UI buttons in CharacterImageLibrary / CreateJobForm / character detail map to existing endpoints (verified against OpenAPI in 05-matrix).

## Backend capabilities with NO UI (reverse gap)
- `POST …/images/upload-reference` — **no UI control** (file picker + synthetic attestation). HIGH.
- `POST …/images/{img}/moderate` — **no UI control** (approve/reject). HIGH.
- These are reachable only via API/script, so the "gated upload + moderation" compliance flow is effectively dark in the product.

## Buttons blocked at runtime (present but non-functional now)
- **"Generate variation"** (generate-consistent): disabled in UI until both canonical refs exist; for all 5 seeded characters it would 422. Effectively non-functional today.
- **Video submit** (CreateJobForm → /jobs): functional API, but DAG workers stopped → job never progresses past creation.

## Hardcoded URLs
- `rg localhost|127.0.0.1` over `frontend/lib`, `frontend/components`, `backend/app` → **37 hits**, all in config defaults / dev fallbacks (API base default, CORS list, ollama/comfyui base URLs). No production domain hardcoded in component bodies. The frontend API base is origin-aware (probe) per design.
- `.env`: `COMFYUI_BASE_URL=http://aivideo-model-comfyui-1:8188` (service DNS, correct).

## Assets / icons
- No image/icon asset references audited as broken; UI uses inline glyphs (▭/▯/◻, 🔒, ⚠) and CSS, plus `characterImageContentUrl()` for served PNGs (binary route exists). Character thumbnails depend on `…/images/{id}/content` which is a live route.
- Static placeholder/branding assets not separately verified → NOT VERIFIED (no broken-asset evidence found, but not exhaustively crawled in a browser).

## External / public links
- Cloudflared container present (tunnel) but no hardcoded public domain found in source. Public-hostname behavior (aiv.alba-vision.ro style) is config-driven, not in code → NOT VERIFIED.

## i18n
- `tsc` enforces the EN/RO key union; lint clean. No missing-key crashes detectable statically. New IG-4 keys (`characters.identity.*`, `characters.images.role_*`) added to both dictionaries.
