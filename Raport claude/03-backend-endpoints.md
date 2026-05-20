# 03 — Backend endpoint inventory

Source: live `GET http://localhost:8001/openapi.json` (OpenAPI **valid**). 66 paths under `/api/v1` + legacy `/jobs` aliases + `/healthz`.

## Routers (evidence: `grep APIRouter( backend/app/api/*.py` + `include_router` in main.py)
healthz · jobs (`/jobs` + re-included at `/api/v1`) · uploads (`/api/v1/uploads` + `/api/v1/jobs`) · system (`/api/v1`) · providers · tts · artifacts · script · audio_fit · video · export · qc · characters · secrets.

## Characters + image pipeline (focus area)
| Method | Path | Notes |
|---|---|---|
| GET | /api/v1/characters | list (alphabetical) |
| POST | /api/v1/characters | create |
| GET | /api/v1/characters/available-voices | Phase 23 voice exclusivity |
| GET | /api/v1/characters/lookups | dropdown catalog |
| GET/PUT/DELETE | /api/v1/characters/{id} | CRUD |
| POST | /api/v1/characters/{id}/clone | Phase 24 |
| POST | /api/v1/characters/{id}/status | Phase 23 lifecycle transition |
| GET | /api/v1/characters/{id}/images | gallery |
| POST | /api/v1/characters/{id}/images/generate | legacy generate |
| POST | …/images/generate-initial | **IG-2 — VERIFIED produces real PNG** |
| POST | …/images/generate-consistent | IG-2 — 422 (no full-body ref) |
| POST | …/images/upload-reference | IG-5 — live, **no UI** |
| POST | …/images/{img}/moderate | IG-5 — live, **no UI** |
| POST | …/images/{img}/set-main-reference | canonical face |
| POST | …/images/{img}/set-full-body-reference | canonical full-body |
| POST | …/images/{img}/{accept,reject,archive} | review |
| GET | …/images/{img}/content | binary |
| GET | …/script-context, …/videos | aux |

## Providers / TTS / LLM
`/api/v1/providers`, `/providers/{llm,tts,image-generators,video-generators,audio-processors,image-processors}`, `/providers/{category}/{id}` + `/health-check`, `/providers/tts/{id}/sample.wav`. LLM order verified: **`ollama_qwen3_6_27b-q4` first (configured)** then template.

## Jobs / video (pipeline stopped at runtime)
`/api/v1/jobs` (+ legacy `/jobs`): list/create/from-inputs/get/patch/delete/cancel/retry + progress/timeline/artifacts/compliance-events/qc-report/final-export/summary. `/api/v1/video/generate`, `/api/v1/export/finalize`, `/api/v1/qc/inspect`, `/api/v1/audio/fit-check`, `/api/v1/script/generate`, `/api/v1/tts/generate`.

## System / secrets / settings
`/api/v1/system/{status,logs/backend,wrappers,technical-architecture[.md]}`, `/api/v1/secrets` (CRUD + test), `/api/v1/settings/ui`, `/api/v1/config/{languages,ui-options}`, `/api/v1/stages`, `/api/v1/artifact-types`.

## Findings
- **Duplicate surface:** `/jobs/*` AND `/api/v1/jobs/*` both exposed (main.py includes jobs.router twice). MEDIUM.
- CORS restricted to localhost:3000/3001/3010 (+127.0.0.1) — fine for dev (`backend/app/core/config.py:32`).
- All endpoints documented in OpenAPI (the Phase 10C api-surface test enforces parity; 926 tests pass).
