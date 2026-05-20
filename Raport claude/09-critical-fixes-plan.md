# 09 — Critical fixes plan (audit-only; not executed)

Ordered by leverage. Effort: S/M/L. "Blocks demo" = blocks an internal identity-image demo.

| # | Fix | Sev | Effort | Blocks demo | Blocks prod |
|---|---|---|---|---|---|
| 1 | Install ComfyUI InstantID (or PuLID-Flux) custom nodes + deps (insightface, onnxruntime); download InstantID ip-adapter + ControlNet + antelopev2 weights; add compose mounts (`custom_nodes`, `models/{instantid,controlnet,insightface}`). | CRIT | L | YES | YES |
| 2 | Per character: generate a full-body candidate (generate-initial) → `set-full-body-reference` so generate-consistent stops 422-ing. | CRIT | M | YES | YES |
| 3 | Wire the upload-reference + moderate UI (file picker + synthetic-attestation checkbox + approve/reject) so the compliance safeguard is reachable. | HIGH | M | NO | YES |
| 4 | Commit the 86-file working tree on a feature branch in reviewable chunks (image pipeline, lifecycle, migrations). | HIGH | S | NO | YES |
| 5 | Persist image-pipeline audit events to a durable store (not just the `image.audit` logger). | MED | M | NO | YES |
| 6 | Backfill `character_images.role` for existing canonical-face rows (currently all `generated_variation`). | MED | S | NO | NO |
| 7 | Decide CORS + public exposure policy for the Cloudflare tunnel; lock origins for prod. | MED | S | NO | YES |
| 8 | Deprecate the duplicate unprefixed `/jobs` route surface. | MED | S | NO | NO |
| 9 | Re-run a portrait video job to re-establish the 720×1280 mobile evidence (after DAG restart). | MED | S | NO | NO |
| 10 | Rebuild backend image so the corrected migration revision id (`0010_ig3_image_meta`) is baked in (DB already at 0010; image still has the long id). | LOW | S | NO | NO |
| 11 | Resolve InsightFace non-commercial license question before any commercial drift-scoring use. | LOW (legal) | S | NO | YES |
| 12 | Remove stray empty `Raport/` dir; triage 36 TODO/FIXME. | LOW | S | NO | NO |

## Sequencing for an identity-image demo
1 → 2 → (smoke generate-consistent) → 3. Items 4–12 are hardening for production, not demo blockers (except 3 for the compliance story).

## Note on the 24 GB box
PuLID-FLUX will not co-reside with the LLM/lipsync models on 24 GB (documented constraint). For a 24 GB demo use the SDXL-InstantID workflow (≈10 GB). PuLID-FLUX is for the planned 128 GB server.
