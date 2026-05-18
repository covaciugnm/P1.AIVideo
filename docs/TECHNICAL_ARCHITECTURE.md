# Technical Architecture — P1.AIVideo

> Snapshot 2026-05-18. Multi-agent Docker pipeline for synthetic-person reels
> with full character/persona system, 11 video generators, 5 image generators,
> chunked Romanian TTS, and DB-backed API key vault.

This document is served by the backend at
`GET /api/v1/system/technical-architecture` and surfaced in the UI under the
**Technical** menu entry. Use the in-page search box (or your browser's `Ctrl+F`)
to jump to a specific layer.

---

## 1. High-level layers

```
┌──────────────────────────────────────────────────────────────────────┐
│  Browser (Next.js 14 / React 18, TS, vanilla CSS, i18n RO + EN)      │
└─────────────┬────────────────────────────────────────────────────────┘
              │  HTTPS  /api/v1/*    (fetch via frontend/lib/api.ts)
┌─────────────▼────────────────────────────────────────────────────────┐
│  FastAPI backend  (uvicorn, pydantic v2, structlog)                  │
│    routers ─► services ─► SQLAlchemy async ─► Postgres 16            │
│             └► provider_registry (metadata-only)                     │
│             └► secrets_service  ──► api_secrets table                │
│             └► httpx ──► model-* HTTP wrappers (GPU)                 │
└─────────────┬────────────────────────────────────────────────────────┘
              │ Redis Streams (queue topics) + httpx
┌─────────────▼────────────────────────────────────────────────────────┐
│  Orchestrator + 5 CPU agents + ≥ 14 GPU wrappers (opt-in profiles)   │
│    /storage/inputs  +  /storage/artifacts  (shared named volumes)    │
│    /models/*  (read-only, host-mounted weights)                      │
└──────────────────────────────────────────────────────────────────────┘
```

- **No browser → wrapper traffic**: every model call leaves through the
  backend so credentials and access checks stay server-side.
- **Metadata-only**: `provider_registry.py` never imports torch/diffusers and
  never opens sockets — status is derived from env vars and on-disk checks.
- **Compose profiles**: heavy GPU services are off by default; bring them up
  per-need (`--profile sdxl`, `--profile sadtalker`, …).

---

## 2. Backend (`backend/app/`)

### 2.1 API routers (14)

| Router file              | Prefix               | What it owns                                                                 |
|--------------------------|----------------------|------------------------------------------------------------------------------|
| `healthz.py`             | `/healthz`           | Liveness + version                                                           |
| `jobs.py`                | `/jobs`, `/api/v1`   | Job CRUD, status, progress, artifacts, recovery actions                      |
| `uploads.py`             | `/api/v1/uploads`    | Audio/image/text uploads + `/api/v1/jobs/from-inputs` composite              |
| `system.py`              | `/api/v1`            | Stages, artifact types, UI options, language config, UI settings, status     |
| `providers.py`           | `/api/v1/providers`  | Provider catalog (all categories), per-category lists, DB overrides          |
| `tts.py`                 | `/api/v1/tts`        | Chunked F5TTS-Ro + Piper preview/generate                                    |
| `artifacts.py`           | `/api/v1/artifacts`  | Stream artifact bytes                                                        |
| `script.py`              | `/api/v1/script`     | Script preview (template / LLM)                                              |
| `audio_fit.py`           | `/api/v1/audio`      | Duration-fit check against `target_duration_seconds`                         |
| `video.py`               | `/api/v1/video`      | Video generation contract (planning surface)                                 |
| `export.py`              | `/api/v1/export`     | ffmpeg-based finalization                                                    |
| `qc.py`                  | `/api/v1/qc`         | On-demand media QC                                                           |
| `characters.py`          | `/api/v1/characters` | Persona CRUD, image library, snapshots, script context                       |
| `secrets.py`             | `/api/v1/secrets`    | DB-backed API key vault (`save`, `list`, `test` probes)                      |

### 2.2 Services (18)

`provider_registry.py` (≈ 1.2k LOC), `job_service.py`, `character_service.py`,
`character_image_service.py`, `character_lookups.py`,
`character_script_context.py`, `secrets_service.py`, `artifact_service.py`,
`upload_service.py`, `audio_conversion.py`, `final_export.py`,
`media_qc.py`, `video_inspection.py`, `subtitle_service.py`,
`feature_provider_service.py`, `queue_publisher.py`, `stage_run_service.py`,
plus the `image_providers/` subpackage (per-backend adapters).

### 2.3 Pydantic schemas (7)

`api_secret`, `character`, `compliance`, `job`, `job_views`, `providers`,
`uploads`. All requests/responses are pydantic v2; OpenAPI is generated
automatically at `/docs`.

### 2.4 DB models (11)

Listed in `backend/app/db/models.py`. See §4 for tables.

---

## 3. Frontend (`frontend/`)

### 3.1 Routes (`app/`)

| Path                     | Purpose                                              |
|--------------------------|------------------------------------------------------|
| `/` (`page.tsx`)         | Dashboard: create-job form, stages, artifacts        |
| `/jobs`, `/jobs/[id]`    | Job list + detail with logs, recovery, artifacts     |
| `/jobs/new`              | Composite "from-inputs" form                         |
| `/uploads`               | Upload queue                                         |
| `/characters`            | Persona CRUD + galerie                               |
| `/settings`              | Operator settings, keys                              |
| `/technical-help`        | **This document** (search + markdown render)         |

### 3.2 Components (≈ 66 files)

Forms (`CreateJobForm.tsx`, `CharacterForm.tsx`),
jobs (`JobRecoveryControls.tsx`, `StageTimeline.tsx`, `ProgressBar.tsx`),
providers (`ProvidersSection.tsx`, `ProviderTestPanel.tsx`,
`ProviderStatusBadge.tsx`), media previews (`VideoArtifactPreview.tsx`,
`AudioPreview.tsx`, `ArtifactTable.tsx`),
characters (`CharacterImageLibrary.tsx`), help (`HelpOverlay.tsx`,
`HelpContext.tsx`, `HelpButton.tsx`, `HelpHint.tsx`),
sidebars (`RightSidebar.tsx`, `SidebarTabs.tsx`, `LogsPanel.tsx`),
config (`SettingsPanel.tsx`, `KeysPanel.tsx`, `LanguageSwitcher.tsx`).

### 3.3 Libraries (`lib/`)

`api.ts` (HTTP client), `types.ts` (interfaces mirroring backend pydantic),
`characters.ts`, `customProviders.ts`, `settings.ts`, `secrets.ts`,
`format.ts`, `log-bus.ts`, `usePolling.ts`, plus
`i18n/` (`LanguageContext.tsx`, `dictionaries/{ro,en}.ts`, `types.ts`).

### 3.4 i18n parity

`tests/integration/test_phase11a_i18n_dictionaries.py` enforces key-for-key
parity between `ro.ts` and `en.ts`. Tooltips read the active language via
`HelpHint`/`HelpContext`, so help text follows the UI switcher live.

---

## 4. Database (PostgreSQL 16, async)

| Table                | Key fields (excerpt)                                                                | Source migration |
|----------------------|--------------------------------------------------------------------------------------|------------------|
| `jobs`               | id, user_id, brief_json, status, video_language, recovery_metadata, character_id, character_snapshot, created/updated_at | 0001 → 0004      |
| `artifacts`          | id, job_id, artifact_type, mime_type, uri, size_bytes, duration_seconds              | 0001             |
| `stage_runs`         | id, job_id, handler_name, status, started_at, finished_at                            | 0001             |
| `compliance_events`  | id, job_id, event_type, decision, metadata                                            | 0001             |
| `operator_settings`  | singleton row: language, ui_options_json                                              | 0003             |
| `characters`         | id, name, profile_json, soft_delete, current_version                                  | 0004             |
| `character_versions` | id, character_id, profile_json, created_at                                            | 0004             |
| `character_images`   | id, character_id, provider_id, file_path, status, cache_key                           | 0004             |
| `character_videos`   | id, character_id, artifact_id, duration, codecs                                       | 0004             |
| `feature_providers`  | id, category, provider_json                                                           | 0004             |
| `api_secrets`        | id, provider_id, value, vault, test_status, test_at                                   | 0005             |

### Alembic migrations

| Rev      | Title                                  | Highlights                                            |
|----------|----------------------------------------|-------------------------------------------------------|
| `0001`   | initial                                | jobs / artifacts / stage_runs / compliance            |
| `0002`   | phase8d recovery metadata              | `jobs.recovery_metadata` JSON for cancel / retry      |
| `0003`   | phase11a language subtitles            | `operator_settings` + `jobs.video_language`           |
| `0004`   | phase12 characters personas            | characters, versions, images, videos, feature_providers |
| `0005`   | phase12x api secrets                   | `api_secrets` (DB-backed API key vault)               |

---

## 5. Docker topology (`docker/compose.dev.yml`)

### 5.1 Core infra (always on)

| Service     | Image                       | Host port  | Volume        |
|-------------|-----------------------------|------------|---------------|
| `postgres`  | `postgres:16-alpine`        | 5433       | postgres_data |
| `redis`     | `redis:7-alpine`            | 6380       | redis_data    |
| `minio`     | `minio/minio:latest`        | 9000, 9001 | minio_data    |
| `backend`   | build `docker/backend`      | 8001       | inputs_data, artifacts_data |
| `frontend`  | build `docker/frontend`     | 3000       | —             |
| `orchestrator` | build `docker/agents`    | —          | inputs_data, artifacts_data |

### 5.2 CPU agents (always on)

`agent-scriptwriter`, `agent-editor`, `agent-qc`, `agent-publisher`,
`agent-compliance` — all built from `docker/agents/Dockerfile`, all share
the `inputs_data` + `artifacts_data` named volumes and `../models:/models:ro`
for read-only weights.

### 5.3 GPU agents (profile `gpu`)

`agent-voice`, `agent-face`, `agent-lipsync`, `model-llm` — built from
`docker/agents/Dockerfile.cuda`. Bring them up with
`docker compose -f docker/compose.dev.yml --profile gpu up -d`.

### 5.4 Image generator wrappers

| Service           | Port | Profile     | Model root (`/models/...`)       |
|-------------------|------|-------------|----------------------------------|
| `model-sdxl`      | 8063 | `sdxl`      | `image/sdxl/sdxl-base-1.0`       |
| `model-flux`      | 8064 | `flux`      | `image/flux/FLUX.1-schnell`      |
| `model-sd35`      | 8065 | `sd35`      | `image/sd35/sd35-large` (gated)  |
| `model-comfyui`   | 8066 | `comfyui`   | `image/comfyui/...`              |
| `model-a1111`     | 7860 | `a1111`     | `image/a1111/sd-v1-*` (limited)  |

### 5.5 Lip-sync / talking-head wrappers

| Service             | Port | Profile        | Notes                                       |
|---------------------|------|----------------|---------------------------------------------|
| `model-sadtalker`   | 8062 | `sadtalker`    | Real DAG runtime (Phase 11H)                |
| `model-wav2lip`     | 8068 | `wav2lip`      | Fast lipsync                                |
| `model-musetalk`    | 8069 | `musetalk`     | Real-time lipsync                           |
| `model-liveportrait`| 8070 | `liveportrait` | Motion-driven portrait                      |
| `model-echomimic`   | 8074 | `echomimic`    | Half-body gestures + lipsync                |
| `model-hallo`       | 8075 | `hallo`        | HD/4K talking head                          |

### 5.6 Video generator wrappers

| Service              | Port | Profile        | Notes                                                 |
|----------------------|------|----------------|-------------------------------------------------------|
| `model-svd`          | 8071 | `svd`          | Stable Video Diffusion (img→vid)                      |
| `model-animatediff`  | 8072 | `animatediff`  | AnimateDiff over SDXL (txt→vid)                       |
| `model-ltx`          | 8073 | `ltx`          | LTX-Video (real-time txt→vid)                         |
| `model-hunyuanvideo` | 8076 | `hunyuan`      | HunyuanVideo (4-bit BNB option via `HUNYUAN_QUANTIZE`)|
| `model-mochi`        | 8077 | `mochi`        | Mochi-1 (4-bit BNB option via `MOCHI_QUANTIZE`)       |

### 5.7 TTS wrapper

| Service        | Port | Profile  | Notes                                            |
|----------------|------|----------|--------------------------------------------------|
| `model-tts-ro` | 8061 | `tts-ro` | F5TTS Romanian; chunked synthesis without limits |

### 5.8 Named volumes

- `postgres_data`, `redis_data`, `minio_data` — infra
- `inputs_data`  → `/storage/inputs`  (uploads / staged audio + images)
- `artifacts_data` → `/storage/artifacts` (per-job outputs)
- Host bind: `../models:/models:ro` (per-wrapper weights, read-only)

---

## 6. Provider registry (`backend/app/services/provider_registry.py`)

| Category            | Count | Notable IDs                                                              |
|---------------------|-------|--------------------------------------------------------------------------|
| `image_generator`   | 16    | mock, flux_local, sd35_local, sdxl_local, comfyui_local, a1111_local + 10 hosted |
| `video_generator`   | 13    | sadtalker, wav2lip, musetalk, liveportrait, echomimic, hallo, svd, animatediff, ltx_video, hunyuan_video, mochi, local_http_video, external_video_api |
| `tts`               | 3+    | piper_ro, f5tts_ro, hosted OpenAI / Google                                |
| `audio_processor`   | 5     | extract, upsample, normalize, loudness, silence trim                      |
| `image_processor`   | 5     | resize, jpeg quality, convert, strip metadata, bg-removal                 |
| `scriptwriter` (LLM)| 8     | template, mock, ollama, vllm, openai_compatible, openai, anthropic, local_http |

Status semantics: `available` (works without setup) · `configured`
(env / DB key present, expect runtime to work) · `not_implemented`
(catalog stub).

---

## 7. Dependencies

### 7.1 Python (`backend/pyproject.toml`)

`fastapi ≥ 0.115`, `uvicorn[standard] ≥ 0.30`, `pydantic ≥ 2.7`,
`pydantic-settings ≥ 2.4`, `sqlalchemy[asyncio] ≥ 2.0.30`,
`asyncpg ≥ 0.29`, `aiosqlite ≥ 0.20`, `alembic ≥ 1.13`,
`redis ≥ 5.0`, `httpx ≥ 0.27`, `pyyaml ≥ 6.0`, `structlog ≥ 24.1`,
`python-multipart ≥ 0.0.9`. Optional extras `[dev]`, `[tts]`.

### 7.2 Node (`frontend/package.json`)

`next@14.2.35`, `react@18.3.1`, `react-dom@18.3.1`, TS 5.5.

### 7.3 Wrappers

Each `docker/model-*/requirements.txt` pins its own torch / diffusers /
transformers / accelerate / bitsandbytes / imageio stack. Common pattern:
`nvidia/cuda:12.8.1-runtime-ubuntu22.04` → `torch==2.7.1+cu128` (Blackwell
sm_120 requires cu128 on this hardware).

---

## 8. Tests

`tests/` ≈ 66 files. Layout:

- `tests/unit/` — pure schema / helper tests
- `tests/integration/` — FastAPI client + sqlite DB (~50 files)
- `tests/e2e/` — full pipeline with real media (~8 files)
- `tests/fixtures/` — reusable factories
- `conftest.py` — async DB + httpx test client

Baseline: **883 passed, 12 skipped** as of 2026-05-18.

---

## 9. External integrations & env vars

### 9.1 HuggingFace-gated weights

`black-forest-labs/FLUX.1-schnell` (token-gated, free),
`stabilityai/stable-diffusion-3.5-large` (gated, accept license),
`stabilityai/stable-video-diffusion-img2vid`,
`genmoai/mochi-1-preview`, `tencent/HunyuanVideo`. Tokens live in
`api_secrets` and are injected into wrappers via env at compose time.

### 9.2 Key env vars (`.env`)

- Core ports: `BACKEND_PORT`, `FRONTEND_PORT`, `POSTGRES_PORT`, `REDIS_PORT`
- LLM scripts: `SCRIPTWRITER_BACKEND`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`
- Storage: `UPLOADS_LOCAL_ROOT`, `ARTIFACTS_LOCAL_ROOT`, `MINIO_*`
- Wrapper URLs: `SDXL_BASE_URL`, `FLUX_BASE_URL`, `SD35_BASE_URL`,
  `SADTALKER_BASE_URL`, `WAV2LIP_BASE_URL`, `MUSETALK_BASE_URL`,
  `LIVEPORTRAIT_BASE_URL`, `ECHOMIMIC_BASE_URL`, `HALLO_BASE_URL`,
  `SVD_BASE_URL`, `ANIMATEDIFF_BASE_URL`, `LTX_BASE_URL`,
  `HUNYUAN_BASE_URL`, `MOCHI_BASE_URL`
- TTS: `F5TTS_RO_BASE_URL`, `F5TTS_RO_CHUNK_MAX_CHARS` (default 180)
- Safety: `ALLOW_MODEL_AUTODOWNLOAD=false`,
  `SADTALKER_ENABLE_REAL_INFERENCE=false`
- Quantization: `HUNYUAN_QUANTIZE=int4`, `MOCHI_QUANTIZE=int4`

---

## 10. Pipeline (job lifecycle)

```
[POST /api/v1/jobs/from-inputs]
        │  validates uploads + consent + character snapshot
        ▼
   jobs.status = pending_compliance
        │  agent-compliance approves
        ▼
   jobs.status = accepted   ──► DAG dispatch via Redis Streams
        │
        ├─► agent-scriptwriter (LLM)        ──► artifact: script.txt
        ├─► agent-voice / model-tts-ro      ──► artifact: audio.wav (chunked)
        ├─► agent-face / model-{flux,sdxl,…}──► artifact: face.png
        ├─► agent-lipsync / model-{sadtalker,wav2lip,…}
        │                                    ──► artifact: video.mp4
        ├─► agent-editor + agent-publisher  ──► final.mp4
        └─► agent-qc                        ──► QC report
        ▼
   jobs.status = published   (artifacts streamable via /api/v1/artifacts)
```

Every stage writes a `stage_runs` row. Failures attach to
`jobs.recovery_metadata` with category (`runtime_missing`,
`assets_missing`, `gpu_unavailable`, `generation_failed`, `storage_failed`)
so the UI can offer targeted retry actions.

---

## 11. Operator commands (Makefile excerpts)

```bash
make backend.up           # start backend container
make frontend.up          # start frontend container
make model-sdxl.up        # GPU wrapper
make model-sadtalker.up   # SadTalker GPU wrapper
make model-tts-ro.up      # F5TTS Romanian
make model-flux.up        # FLUX.1-schnell wrapper
make model-sd35.up        # SD3.5 large (gated)
make model-hunyuan.up     # HunyuanVideo (4-bit option)
make smoke                # quick health checks
make test                 # pytest tests/
```

Build/up/down/logs/smoke targets are generated by the `_mk_wrapper_targets`
macro so every wrapper follows the same convention.

---

## 12. Where to look

| Topic                       | File                                                       |
|-----------------------------|------------------------------------------------------------|
| Provider catalog            | `backend/app/services/provider_registry.py`                |
| Chunked TTS                 | `backend/app/api/tts.py` (`_chunk_script_for_tts`)          |
| Character snapshot in job   | `backend/app/services/job_service.py`                       |
| DB-backed secrets           | `backend/app/services/secrets_service.py`                   |
| i18n dictionaries           | `frontend/lib/i18n/dictionaries/{ro,en}.ts`                 |
| Help tooltips               | `frontend/components/HelpHint.tsx` + `lib/help/dictionaries`|
| Compose                     | `docker/compose.dev.yml`                                    |
| Per-wrapper Dockerfiles     | `docker/model-*/Dockerfile`                                 |
| Migrations                  | `backend/alembic/versions/0001..0005_*.py`                  |
| Tests                       | `tests/{unit,integration,e2e}`                              |
