# Technical Architecture — P1.AIVideo

> Snapshot 2026-05-26. Multi-agent Docker pipeline for synthetic-person reels
> with full character/persona system, 11 video generators, 5 image generators,
> chunked Romanian TTS, a DB-backed API key vault, and JWT auth + RBAC with a
> persistent security-audit trail surfaced live in the right-sidebar log panels.

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
- **Auth + RBAC (always on in prod)**: JWT bearer auth, role guards
  (`require_active_user` / `require_operator_or_above` / `require_super_admin`),
  a protected super-admin bootstrapped at startup, and a self-service
  registration flow that always lands `pending`/`operator`/inactive until an
  admin approves. `P1_AUTH_ENABLED=false` only for the legacy test-suite.
- **Security observability**: `security_audit_service` writes a structured
  `security.audit` log AND a `security_audit_events` row for every auth/RBAC/
  secret/user-admin event (denials included), with sensitive keys redacted. An
  in-memory root-logger ring buffer (`core/log_buffer.py`) feeds the backend
  log sidebar via `GET /api/v1/system/logs/backend`.

---

## 2. Backend (`backend/app/`)

### 2.1 API routers (17)

| Router file              | Prefix               | What it owns                                                                 |
|--------------------------|----------------------|------------------------------------------------------------------------------|
| `healthz.py`             | `/healthz`           | Liveness + version (public)                                                  |
| `auth.py`                | `/api/v1/auth`       | login, register, me, change-password, logout (public; fully audited)        |
| `users.py`               | `/api/v1/users`      | User admin — approve/reject/suspend/reactivate/soft-delete (super-admin)     |
| `audit.py`               | `/api/v1/audit`      | Read the persistent security-audit trail (super-admin)                       |
| `jobs.py`                | `/jobs`, `/api/v1`   | Job CRUD, status, progress, artifacts, recovery actions (create = operator+) |
| `uploads.py`             | `/api/v1/uploads`    | Audio/image/text uploads + `/api/v1/jobs/from-inputs` composite              |
| `system.py`              | `/api/v1`            | Stages, artifact types, UI options, language config, status, **backend log buffer**, technical-architecture doc |
| `providers.py`           | `/api/v1/providers`  | Provider catalog (all categories), per-category lists, DB overrides          |
| `tts.py`                 | `/api/v1/tts`        | Chunked F5TTS-Ro + Piper preview/generate                                    |
| `artifacts.py`           | `/api/v1/artifacts`  | Stream artifact bytes                                                        |
| `script.py`              | `/api/v1/script`     | Script preview (template / LLM)                                              |
| `audio_fit.py`           | `/api/v1/audio`      | Duration-fit check against `target_duration_seconds`                         |
| `video.py`               | `/api/v1/video`      | Video generation contract (planning surface)                                 |
| `export.py`              | `/api/v1/export`     | ffmpeg-based finalization                                                    |
| `qc.py`                  | `/api/v1/qc`         | On-demand media QC                                                           |
| `characters.py`          | `/api/v1/characters` | Persona CRUD, image library, snapshots, script context                       |
| `secrets.py`             | `/api/v1/secrets`    | DB-backed API key vault — `save`/`list`/`test`/`delete` (super-admin, audited) |

Router mounting (`main.py`): `healthz` + `auth` are public; product routers are
guarded by `require_active_user`; `secrets`/`users`/`audit` require super-admin.

### 2.2 Services (≈ 27 + image_providers/)

**Core/business:** `provider_registry.py` (≈ 1.2k LOC), `job_service.py`,
`stage_run_service.py`, `artifact_service.py`, `upload_service.py`,
`queue_publisher.py`, `feature_provider_service.py`, `docker_control.py`.
**Auth & security:** `auth_service.py`, `user_service.py`,
`security_audit_service.py`, `secrets_service.py`.
**Characters:** `character_service.py`, `character_image_service.py`,
`character_lookups.py`, `character_script_context.py`,
`character_prompt_builder.py`.
**Media:** `audio_conversion.py`, `final_export.py`, `media_qc.py`,
`video_inspection.py`, `subtitle_service.py`, `tts_job_service.py`,
`translator.py`.
**Image gen helpers:** `image_workflow_select.py`, `image_audit.py`,
`image_face_score.py`, plus the `image_providers/` subpackage (per-backend
adapters: base, dispatch, mock, hosted_stub, local_wrapper_stub, kontext_stub).

### 2.3 Pydantic schemas (8)

`api_secret`, `auth`, `character`, `compliance`, `job`, `job_views`,
`providers`, `uploads`. (`auth` never exposes `password_hash`.) All
requests/responses are pydantic v2; OpenAPI is generated automatically at `/docs`.

### 2.4 DB models (14 tables)

Defined as one class per file under `backend/app/models/*.py` (declarative base
in `models/base.py`). See §4 for the table list.

---

## 3. Frontend (`frontend/`)

### 3.1 Routes (`app/`)

| Path                       | Purpose                                              |
|----------------------------|------------------------------------------------------|
| `/` (`page.tsx`)           | Public landing / presentation (no auth, no shell)    |
| `/login`, `/register`      | Auth forms (logBus-instrumented; show/hide password) |
| `/jobs`, `/jobs/[jobId]`   | Job list + detail with logs, recovery, artifacts     |
| `/jobs/new`                | Composite "from-inputs" create form                  |
| `/jobs/[jobId]/edit`       | Edit a recoverable job (Phase 11B edit policy)       |
| `/uploads`                 | Upload queue                                         |
| `/characters`, `/characters/new`, `/characters/[id]` | Persona library / create / detail+edit+image library |
| `/settings`                | Operator settings, providers, keys                   |
| `/users`                   | User administration (super-admin)                    |
| `/technical-help`          | **This document** (search + markdown render)         |

### 3.2 Components (≈ 57 files)

Forms (`CreateJobForm.tsx`, `CharacterForm.tsx`),
jobs (`JobRecoveryControls.tsx`, `StageTimeline.tsx`, `ProgressBar.tsx`,
`FinalExportCard.tsx`, `QcReportCard.tsx`, `ComplianceEvents.tsx`),
providers (`ProvidersSection.tsx`, `CustomProvidersSection.tsx`,
`ProviderTestPanel.tsx`, `ProviderStatusBadge.tsx`, `BackendStatusBadge.tsx`),
media previews (`VideoArtifactPreview.tsx`, `AudioPreview.tsx`, `AuthImage.tsx`,
`AuthVideo.tsx`, `ArtifactTable.tsx`), characters (`CharacterImageLibrary.tsx`,
`CharacterIdentityProfile.tsx`, `CharacterVideoLinks.tsx`),
help (`HelpOverlay/Context/Button/Hint.tsx`),
**right sidebar + logging** (`RightSidebar.tsx`, `SidebarTabs.tsx`,
`LogsContext.tsx`, `LogsPanel.tsx` (frontend logBus), `BackendLogsPanel.tsx`
(polls `/system/logs/backend`), `ServicesPanel.tsx`),
config (`SettingsPanel.tsx`, `SettingsContext.tsx`, `KeysPanel.tsx`,
`LanguageSwitcher.tsx`), shell (`AppFrame.tsx`, `LocalizedNav.tsx`,
`Providers.tsx`).

### 3.3 Libraries (`lib/`)

`api.ts` (HTTP client, logs to logBus + handles 401), `auth.ts` (token +
current-user storage), `types.ts` (interfaces mirroring backend pydantic),
`characters.ts`, `users.ts`, `secrets.ts`, `customProviders.ts`, `settings.ts`,
`format.ts`, `log-bus.ts` (pub/sub logging backbone), `usePolling.ts`, plus
`i18n/` (`LanguageContext.tsx`, `dictionaries/{ro,en}.ts`, formatters, types)
and `help/` (RO/EN help corpus — 30 topics — + selector + types).

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
| `users`              | id, username, email, password_hash, role, user_status, is_active, is_protected, approved/suspended/deleted_by + timestamps | 0011 |
| `security_audit_events` | id, event_type, severity, result, actor_user_id/username/role, target_type/id, endpoint, method, request_id, ip, user_agent, reason, metadata_json | 0012 |
| `tts_jobs`           | id, status, script_text, voice_id, chunk progress, local_path, error — async chunked F5 jobs that survive restarts | 0013 |

### Alembic migrations

| Rev      | Title                                  | Highlights                                            |
|----------|----------------------------------------|-------------------------------------------------------|
| `0001`   | initial                                | jobs / artifacts / stage_runs / compliance            |
| `0002`   | phase8d recovery metadata              | `jobs.recovery_metadata` JSON for cancel / retry      |
| `0003`   | phase11a language subtitles            | `operator_settings` + `jobs.video_language`           |
| `0004`   | phase12 characters personas            | characters, versions, images, videos, feature_providers |
| `0005`   | phase12x api secrets                   | `api_secrets` (DB-backed API key vault)               |
| `0006`   | phase16 face_locked                    | `characters.face_locked` (identity immutability)     |
| `0007`   | phase21 job_type + scene_plan          | `jobs.job_type`, `jobs.scene_plan` (pipeline variants) |
| `0008`   | phase22 orientation                    | `jobs.orientation` (landscape / portrait)            |
| `0009`   | phase24 full-body reference            | character full-body reference image                  |
| `0010`   | phase_ig3 image role metadata          | image role/metadata columns                          |
| `0011`   | users / auth                           | `users` table (auth, RBAC, registration lifecycle)   |
| `0012`   | security audit events                  | `security_audit_events` (persistent audit trail)     |
| `0013`   | tts jobs                               | `tts_jobs` (async chunked F5 generation)             |

---

## 5. Docker topology (`docker/compose.dev.yml`)

### 5.1 Core infra (always on)

| Service     | Image                       | Host port  | Volume        |
|-------------|-----------------------------|------------|---------------|
| `postgres`  | `postgres:16-alpine`        | 5433       | postgres_data |
| `redis`     | `redis:7-alpine`            | 6380       | redis_data    |
| `minio`     | `minio/minio:latest`        | 9000, 9001 | minio_data    |
| `backend`   | build `docker/backend`      | 8001       | inputs_data, artifacts_data |
| `frontend`  | build `docker/frontend`     | 3010 (→ container 8010) | —  |
| `orchestrator` | build `docker/agents`    | —          | inputs_data, artifacts_data |
| `model-ollama` | `ollama/ollama:latest`   | 11435      | mounts `models/qwen-gguf` ro; default LLM runtime (`qwen3.6:27b-q4`) |
| `cloudflared`  | `cloudflare/cloudflared` | —          | optional public tunnel (set `CLOUDFLARED_TUNNEL_TOKEN`) |

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

Layout:

- `tests/integration/` — **78 files**, FastAPI client + in-memory SQLite
  (`sqlite+aiosqlite`), one (or more) per phase (`test_phaseNX_*.py`) plus the
  auth/security suite (`test_phase_auth_rbac.py`, `test_phase_audit_logging.py`,
  `test_phase12x_secrets.py`).
- `tests/e2e/` — full-pipeline / real-media tests.
- `tests/fixtures/` — reusable factories.
- `tests/conftest.py` — async DB + httpx test client; defaults to
  `P1_AUTH_ENABLED=false` (the auth/security suite flips it on in its own fixture).

`pytest.ini` sets `asyncio_mode = auto`. Run a phase via Makefile
(`make phase4a-test`, …) or everything via `make test`. **Note:** images bake
their source, so to run tests against edited code use a throwaway container of
`aivideo-backend:latest` with the repo mounted at `/app` (it installs
`backend`/`common`/`agents` editable there), layering `pytest pytest-asyncio
aiosqlite fakeredis httpx`.

---

## 9. External integrations & env vars

### 9.1 HuggingFace-gated weights

`black-forest-labs/FLUX.1-schnell` (token-gated, free),
`stabilityai/stable-diffusion-3.5-large` (gated, accept license),
`stabilityai/stable-video-diffusion-img2vid`,
`genmoai/mochi-1-preview`, `tencent/HunyuanVideo`. Tokens live in
`api_secrets` and are injected into wrappers via env at compose time.

### 9.2 Key env vars (`.env`)

- Core ports: `BACKEND_PORT` (8001), `FRONTEND_PORT` (3010), `POSTGRES_PORT`
  (5433), `REDIS_PORT` (6380)
- Auth / RBAC: `P1_AUTH_ENABLED` (true in prod), `P1_JWT_SECRET`,
  `P1_SUPER_ADMIN_USERNAME`, `P1_SUPER_ADMIN_PASSWORD` (protected super-admin
  bootstrapped at startup)
- LLM scripts: `LLM_BACKEND`, `LLM_MODEL_ID`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`
  (`qwen3.6:27b-q4`), `OLLAMA_FALLBACK_MODEL`, `OPENAI_API_KEY`,
  `ANTHROPIC_API_KEY`
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

## 10. Pipeline (job / video lifecycle)

Phase 21 introduced **three pipeline variants** selected by the
operator via `job_type` (talking_head | scenes_only | news_presenter).
The DAG runner dispatches to the right pipeline YAML based on the
job_type value; downstream stages (qc, publisher) are shared across
all three.

### 10.1 talking_head — 11 stages (default, back-compat)

```
[POST /api/v1/jobs/from-inputs  job_type=talking_head]
   │
   ▼
   pending_compliance ──► policy_gate
                          scriptwriter        (LLM, mode=spoken_script)
                          voice               (Piper or F5 TTS)
                          face                (FLUX / SDXL / SD3.5 / uploaded)
                          identity_guard
                          pre_lipsync_auth    (compliance token mint)
                          lipsync             (SadTalker / Wav2Lip / MuseTalk)
                          editor              (ffmpeg remux + optional subtitle burn-in)
                          qc
                          export_disclosure_validation
                          publisher
   ▼
   published (1.5–25MB MP4 — single talking head)
```

### 10.2 scenes_only — 6 stages (Phase 21)

```
[POST /api/v1/jobs/from-inputs  job_type=scenes_only  scene_plan=[…broll…]]
   │
   ▼
   pending_compliance ──► policy_gate
                          scriptwriter        (mode=spoken_script — back-compat artifact)
                          scene_composer      ┐
                                              ├─ per scene: FLUX image + F5 TTS + ffmpeg zoompan
                                              └─ ffmpeg concat → reel_draft
                          qc                  (consumes editor-aliased output)
                          export_disclosure_validation
                          publisher
   ▼
   published (no character on screen; voiceover over B-roll scenes)
```

### 10.3 news_presenter — 9 stages (Phase 21 hybrid)

```
[POST /api/v1/jobs/from-inputs  job_type=news_presenter  scene_plan=[…presenter+broll…]]
   │
   ▼
   pending_compliance ──► policy_gate
                          scriptwriter
                          face                (character portrait)
                          identity_guard
                          pre_lipsync_auth
                          scene_composer      ┐
                                              ├─ presenter scene: SadTalker lipsync on portrait
                                              ├─ broll scene:    FLUX image + ffmpeg zoompan
                                              ├─ each scene:     per-scene F5 TTS
                                              └─ ffmpeg concat   → reel_draft
                          qc
                          export_disclosure_validation
                          publisher
   ▼
   published (presenter + B-roll interleaved hybrid reel)
```

Every stage writes a `stage_runs` row. Failures attach to
`jobs.recovery_metadata` with category (`runtime_missing`,
`assets_missing`, `gpu_unavailable`, `generation_failed`, `storage_failed`)
so the UI can offer targeted retry actions.

### 10.4 Worker concurrency (Phase 21 fix)

The orchestrator picks the next job via
`SELECT … FOR UPDATE SKIP LOCKED` + `UPDATE status='accepted'` in one
transaction, so the 8 `aivideo-agent-*` containers (each running their
own copy of `run_worker`) cannot race to process the same job. Before
the fix multiple workers would each run the DAG against the same row
and flood the wrappers with duplicate FLUX/TTS calls → GPU OOM.

### 10.5 display_name (operator-facing identifier)

Each video carries a computed `display_name` of the form
`<CharacterName>.<HH.MM>.<AM|PM>.<YYYY.MM.DD>` — e.g.
`Alexandra.Voicu.09.25.AM.2026.05.19`. When no character is bound
(e.g. scenes_only without character_id) the prefix is the literal
`Video.`. The Videos list (`/jobs`) and Dashboard redirect target use
this as the primary column in place of the raw UUID.

---

## 11. Operator commands (Makefile excerpts)

```bash
make up                   # start the dev stack (CPU)        → compose.dev.yml
make up-gpu               # dev stack + GPU overlay           → + compose.gpu.yml
make down                 # stop the stack
make logs                 # tail all services
make ps                   # list running services
make test                 # pytest (full suite)

# Per-wrapper lifecycle (one set per model-*; same verbs everywhere):
make docker-flux-build && make docker-flux-up      # FLUX.1-schnell
make docker-sdxl-up                                # SDXL
make docker-tts-ro-build && make docker-tts-ro-up  # F5TTS Romanian (profile tts-ro)
make docker-musetalk-up                            # MuseTalk lip-sync
make docker-comfyui-up                             # ComfyUI
make docker-<name>-{build,up,down,logs,smoke}      # general convention
```

Every wrapper exposes the same `docker-<name>-{build,up,down,logs,smoke}`
targets. **Bake caveat:** `backend`, `frontend`, `orchestrator`, agent and
`model-*` images COPY their source at build time — after editing code (or this
doc) you must rebuild + recreate the affected service for the change to take
effect in the running container.

---

## 12. Where to look

| Topic                       | File                                                       |
|-----------------------------|------------------------------------------------------------|
| Provider catalog            | `backend/app/services/provider_registry.py`                |
| Chunked TTS                 | `backend/app/api/tts.py` (`_chunk_script_for_tts`)          |
| Character snapshot in job   | `backend/app/services/job_service.py`                       |
| DB-backed secrets           | `backend/app/services/secrets_service.py`                   |
| Auth + RBAC guards          | `backend/app/core/security.py`                              |
| Security audit trail        | `backend/app/services/security_audit_service.py` + `api/audit.py` |
| Backend log buffer (sidebar)| `backend/app/core/log_buffer.py` + `api/system.py` (`/system/logs/backend`) |
| i18n dictionaries           | `frontend/lib/i18n/dictionaries/{ro,en}.ts`                 |
| Help tooltips               | `frontend/components/HelpHint.tsx` + `lib/help/dictionaries`|
| Compose                     | `docker/compose.dev.yml`                                    |
| Per-wrapper Dockerfiles     | `docker/model-*/Dockerfile`                                 |
| Migrations                  | `backend/alembic/versions/0001..0013_*.py`                  |
| Tests                       | `tests/{integration,e2e,fixtures}`                          |
