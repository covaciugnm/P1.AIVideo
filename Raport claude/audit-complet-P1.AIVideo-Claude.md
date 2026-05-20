# Audit complet — P1.AIVideo (Claude, audit-only)

**Date:** 2026-05-20 · **Branch:** main · **Last commit:** `8a54cf1 Phase 12 …` · **Working tree:** 86 uncommitted files
**Method:** evidence-based, re-verified from live runtime / DB / OpenAPI / code / tests. No fixes applied.
**Actual ports (differ from brief):** backend **:8001**, frontend **:3010**, ComfyUI **:8066→8188**, postgres :5433, redis :6380.

Supporting files: `01-project-structure.md`, `02-docker-runtime.md`, `03-backend-endpoints.md`, `04-frontend-routes-ui.md`, `05-frontend-backend-matrix.md`, `06-broken-links-buttons-assets.md`, `07-tests-and-logs.md`, `08-security-compliance.md`, `09-critical-fixes-plan.md`, `findings.json`.

---

## 1. Executive summary
P1.AIVideo's **metadata/control plane is solid and live**: backend healthy (66 `/api/v1` routes, valid OpenAPI, DB reachable), frontend healthy (lint+tsc clean, serves 200), 926 backend tests pass. The **character lifecycle, TTS exclusivity, clone/draft, LLM default, and the new image-provider abstraction are real and verified.** The **new image pipeline produces real images for the INITIAL (SDXL text-to-image) path** — proven with a 1 MB 768×1024 PNG rendered live via ComfyUI.

However, the **headline deliverable — identity-CONSISTENT generation (same synthetic person across scenes) — is NOT functional**: the InstantID/PuLID custom nodes and weights are not installed, and no character has a canonical full-body reference, so `generate-consistent` returns 422 for everyone. The **gated upload + moderation compliance flow has no UI**. The **video/DAG pipeline is stopped** (intentional, pre-128 GB migration). All of this work is **uncommitted on main**.

## 2. Overall verdict
**PARTIALLY READY** — ready for an *internal demo of the control plane + character management + a single SDXL "initial" render*; **NOT READY** to demo the identity-consistent image feature or video generation, and **NOT READY for production**.

## 3. Claim-by-claim verification

| # | Claim | Verified? | Evidence | Risk | Required fix |
|---|---|---|---|---|---|
| 1 | Phase 23 lifecycle (editing/active/retired, transition endpoint) | **YES** | `POST /characters/{id}/status` + `/available-voices` in OpenAPI; 5 chars `active`; live transition smoke earlier | low | — |
| 1b | Exclusive TTS voice per character | **YES** | psql: 5 distinct voices, 0 duplicates | low | — |
| 1c | Immutable fields after activation | PARTIAL (code present, not re-smoked this audit) | `assert_synthetic_only`/immutability code + tests pass | low | re-smoke |
| 2 | Phase 24 full_body ref + lock + clone + draft + migration 0009 | **YES** | columns exist; head=0010>0009; `/clone` live + UI button; draft=editing | low | — |
| 3 | Sorting (chars alpha; videos by char/date) | PARTIAL | chars list alpha (code+data); video sort code present but **0 jobs** to verify | low | re-verify w/ jobs |
| 4 | Mobile 9:16 + responsive + portrait 720×1280 published job | **NOT VERIFIED** | orientation code present; the cited job was deleted (jobs=0) | med | re-run portrait job |
| 5 | LLM default = Qwen3.6 27B first | **YES** | `/providers/llm` → `ollama_qwen3_6_27b-q4` first (configured) | low | — |
| 6 | F5 TTS GPU-agent shared-volume fix | **YES (compose)** | agent-voice/face/lipsync carry inputs_data+artifacts_data+runtime-env | low | agents currently stopped |
| 7 | 5 F5 voices assigned, Sofia on ro_default | **YES** | psql mapping; only 2 female voices for 3 female chars → Sofia=ro_default | low | add 3rd female voice |
| 8 | Image pipeline IG-1…6: 926 tests, migration 0010, routes live, ComfyUI connected, SDXL visible, VRAM-aware, templates, prompt builder, moderation, drift, badges | **MOSTLY YES** | 926 passed; head 0010; routes in OpenAPI; backend→ComfyUI 200; SDXL ckpt visible; VRAM 23.9→fallback; 4 templates; builder+badges present | — | see 8b |
| 8b | Identity-CONSISTENT actually works | **NO / PARTIAL** | InstantID/PuLID nodes+weights absent; all chars lack full-body ref → generate-consistent 422 | **HIGH** | install nodes+weights+refs |
| 9 | ComfyUI `_comment` 500 bug; fix exists but not deployed | **RESOLVED** | logs showed the 500; fix IS deployed (`local_wrapper_stub.py:329`); live generate-initial succeeded | low | — |
| 10 | InstantID/PuLID missing (nodes, weights, mounts, deps, refs) | **CONFIRMED MISSING** | custom_nodes=example only; no instantid/pulid/antelope weights; compose lacks mounts | HIGH | full setup |
| 11 | Video gen stopped; jobs deleted | **CONFIRMED** | no orchestrator/agent containers; jobs count=0 | n/a (intended) | restart on 128 GB box |

## 4. Critical findings
- **C1 — Identity-consistent generation not functional** (InstantID/PuLID nodes+weights absent; no full-body refs; generate-consistent 422). *Blocks demo + prod.*
- **C2 — Video/DAG pipeline non-operational** (orchestrator + all agents stopped; jobs table empty). *Intentional; blocks video demo.*

## 5. High findings
- **H1 — upload-reference + moderate have no UI** (backend live, lib clients unused). Compliance safeguard unreachable in product.
- **H2 — 86-file working tree uncommitted on main** (last commit "Phase 12"). Loss risk; main is dirty.
- **H3 — generate-consistent blocked for all characters** (no canonical full-body reference).

## 6. Medium findings
M1 mobile portrait evidence gone (NOT VERIFIED) · M2 duplicate `/jobs` + `/api/v1/jobs` surface · M3 `character_images.role` backfilled to default for canonical-face rows · M4 36 TODO/FIXME / 22 files · M5 model-comfyui compose lacks custom_nodes/instantid mounts · (sec) image-pipeline audit events log-only, CORS/public exposure undefined for prod.

## 7. Low findings
L1 stray empty `Raport/` dir · L2 backend image still bakes the long 0010 revision id (DB correct) · L3 12 skipped runtime-smoke tests (expected) · L4 InsightFace antelopev2 non-commercial license.

## 8. Backend endpoint inventory → `03-backend-endpoints.md` (66 v1 routes; OpenAPI valid).
## 9. Frontend route/page inventory → `04-frontend-routes-ui.md` (11 pages, 38 components).
## 10. UI button/form/link inventory → `04` + `06`.
## 11. Frontend-backend matrix → `05-frontend-backend-matrix.md` (mandatory matrix).
## 12. Docker/runtime findings → `02-docker-runtime.md`.
## 13. ComfyUI / image pipeline findings
ComfyUI v0.21.1 live, SDXL checkpoint visible, backend connected (200). `generate-initial` produces REAL renders (1 MB 768×1024 PNG, magic `89504e47`). VRAM-aware selection works (23.9 GB → SDXL-InstantID fallback). The `_comment` 500 bug is resolved. **Gap:** identity conditioning (InstantID/PuLID) not installed → consistent path unusable.
## 14. InstantID/PuLID readiness → **NOT READY**: nodes absent, weights absent, compose mounts absent, deps (insightface/onnxruntime) not installed in the ComfyUI image, no per-character full-body refs. See `09` plan items 1–2.
## 15. TTS/persona lifecycle → lifecycle endpoints + exclusivity verified; 5 voices assigned (Sofia ro_default; only 2 female voices is a content gap).
## 16. Video/orchestrator → stopped; jobs empty; code present (`agents/orchestrator`, pipelines/*.yaml). Re-enable via `--profile gpu`.
## 17. Security/compliance → `08-security-compliance.md`. Secrets not in git; synthetic-only gate corrected; gated upload enforced server-side but UI-less; audit log-only.
## 18. Test results → `07`: **926 passed, 12 skipped**; frontend lint+tsc clean; `npm run build`/`npm test` NOT run (NOT VERIFIED).
## 19. Broken links/buttons/assets → `06`: no UI button hits a missing endpoint; reverse gap = upload/moderate have no UI; "Generate variation" + video submit non-functional at runtime; assets not browser-crawled (NOT VERIFIED).
## 20. Missing features → identity-consistent generation runtime; upload/moderation UI; durable image-audit; 3rd female voice; (per spec) FLUX Kontext is an intentional stub.
## 21. Incomplete flows → generate-consistent (refs), upload→moderate→promote (no UI), video submit→render (workers down).
## 22. Recommended fixes → `09-critical-fixes-plan.md`.
## 23. Top 10 urgent problems
1. Identity-consistent generation not functional (InstantID/PuLID nodes+weights). 2. No canonical full-body refs → generate-consistent 422. 3. upload-reference/moderate have no UI. 4. 86 files uncommitted on main. 5. Video/DAG pipeline stopped (no video demo). 6. Image-pipeline audit events log-only (weaker auditability). 7. CORS/public-exposure policy undefined for prod. 8. model-comfyui compose missing InstantID mounts/deps. 9. Mobile portrait evidence gone (NOT VERIFIED). 10. `character_images.role` backfill inaccurate for canonical images.

## 24. Exact commands executed (key)
```
git branch --show-current; git log -1 --oneline; git status --porcelain | wc -l
docker compose --env-file .env -f docker/compose.dev.yml config | (validity)
docker compose --env-file .env -f docker/compose.dev.yml ps
docker ps --filter name=aivideo --format '{{.Names}}\t{{.Ports}}'
curl -sS http://localhost:8001/healthz ; /api/v1/system/status ; /openapi.json
curl -sS http://localhost:8001/api/v1/providers/llm
curl -I http://localhost:3010/characters
docker compose exec backend python -c "...urlopen comfyui/system_stats"  -> 200
curl http://localhost:8066/object_info/CheckpointLoaderSimple
psql: SELECT name,status,default_voice_provider_id,main_reference_image_id,full_body_reference_image_id FROM characters
psql: SELECT role,count(*) FROM character_images GROUP BY role
psql: SELECT version_num FROM alembic_version  -> 0010_ig3_image_meta
curl -X POST .../images/generate-initial  -> real PNG 51e38630 (1012995 bytes, 768x1024)
docker logs aivideo-model-comfyui-1   (the _comment 500, resolved)
find models/ -iname '*instantid*' -o -iname '*pulid*' -o -iname '*antelope*'  -> empty
docker compose exec model-comfyui ls /comfyui/custom_nodes  -> example only
pytest tests/ -q   -> 926 passed, 12 skipped
(frontend) npm run lint -> clean ; npx tsc --noEmit -> clean
rg 'TODO|FIXME|HACK|XXX' ; rg 'localhost|127.0.0.1' ; git check-ignore .env
```

## 25. Files inspected (key)
backend: `app/main.py`, `app/api/*.py`, `app/services/character_image_service.py`, `app/services/character_prompt_builder.py`, `app/services/image_workflow_select.py`, `app/services/image_providers/{base,dispatch,local_wrapper_stub,kontext_stub}.py`, `app/services/{image_audit,image_face_score}.py`, `app/models/character.py`, `app/schemas/character.py`, `app/core/config.py`, `alembic/versions/0010_*`.
frontend: `app/**/page.tsx`, `components/CharacterImageLibrary.tsx`, `components/CreateJobForm.tsx`, `lib/characters.ts`, `lib/i18n/*`.
infra: `docker/compose.dev.yml`, `docker/model-comfyui/Dockerfile`, `.env`, `workflows/comfyui/*`.

## 26. Items NOT verified and why
- Mobile portrait 720×1280 published job — artifact deleted (jobs=0).
- Video DAG end-to-end — workers stopped intentionally.
- `npm run build` (prod build) / frontend unit tests — not run / not configured.
- Browser-level broken-asset/link crawl — not performed (static + 200 only).
- Public Cloudflare hostname behavior — config-driven, not exercised.
- Live ComfyUI identity-consistent render — InstantID/PuLID not installed.
- script.generate / uploads / settings / job-detail endpoints at runtime — live but not re-exercised this audit.
