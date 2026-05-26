# CLAUDE.md — P1.AIVideo

> Orientation guide for working in this repository. Read top-to-bottom once;
> after that, jump to the per-directory tables to find any file fast.

**Application root (the one that runs here):** `/home/cesiro/Documents/P1.AIVideo`
Every Docker image in the `aivideo-*` stack builds from this directory.

---

## ⚠️ 0. TRANSFER NOTE — this copy ships WITHOUT model weights

> If you are reading this on a **transferred copy** of the project: the full
> application **code, structure and config were copied, but `models/` (the
> ~353 GB of model weights) was deliberately EXCLUDED** from the transfer.
> `node_modules/` and `.venv/` were also excluded (regenerable). The directory
> structure is otherwise complete and the app will not run end-to-end until the
> required weights are placed back under `models/` (and the venv + node modules
> are rebuilt). On the target device run `python -m venv` + `pip install -e
> backend -e common -e agents` and `cd frontend && npm install`. The
> `models/*` subfolders are mounted read-only into the `model-*` containers.

### Models actually in use on the source machine (what to restore)

Source host total weights ≈ **353 GB**. The stack that was actively running used
these (the rest are present as alternatives/fallbacks):

| Feature | Model in use (running container) | Weights path | Size |
| :--- | :--- | :--- | :--- |
| **LLM** | Ollama **`qwen3.6:27b-q4`** (fallback `qwen3.5:9b-q4`), via `aivideo-model-ollama-1` | `models/qwen-gguf/` (+ Ollama store outside repo) | 22 GB |
| **TTS (RO)** | **F5-TTS Romanian**, voice `ro_barbat_1_linistit`, via `aivideo-model-tts-ro-1` | `models/tts/f5tts-ro/` | 14 GB |
| **TTS (default)** | Piper synthetic voices (`TTS_BACKEND=piper`, `en_US-amy-medium`) | `models/tts/piper/` | 121 MB |
| **Image gen** | **FLUX** `flux.1-schnell` + **PuLID** (default provider `pulid_flux`), via `aivideo-model-flux-1` | `models/image/flux/`, `models/pulid/`, `models/image/instantid/`, `models/image/insightface/`, `models/image/controlnet/` | 54 + 1.1 + 1.6 + 0.4 + 2.4 GB |
| **Image (alt/fallback)** | SDXL, SD 3.5 | `models/image/sdxl/` (149 GB), `models/image/sd35/` (67 GB) | 216 GB |
| **Image support** | UNet, CLIP, VAE encoders | `models/unet/` (12 GB), `models/clip/` (5.6 GB), `models/vae/` (320 MB) | 18 GB |
| **Lip-sync** | **MuseTalk** running (`aivideo-model-musetalk-1`); `.env` default `sadtalker` | `models/lipsync/musetalk/` (7.7 GB), `models/lipsync/sadtalker/` (2 GB) | 9.7 GB |
| **Lip-sync (alt)** | Hallo, Wav2Lip, LivePortrait | `models/lipsync/{hallo,wav2lip,liveportrait}/` | 13 + 2.3 + 2 GB |
| **Video gen** | **none downloaded** (svd/ltx/mochi/hunyuan/animatediff dirs empty) | `models/video/*` | ~0 |

**Minimum set to make the running config work again** (≈ **97 GB**, skipping the
huge unused SDXL/SD3.5 alternatives): `models/tts/f5tts-ro` + `models/tts/piper`
+ `models/image/flux` + `models/pulid` + `models/image/instantid` +
`models/image/insightface` + `models/image/controlnet` + `models/unet` +
`models/clip` + `models/vae` + `models/lipsync/musetalk` (+ `models/qwen-gguf` if
not re-pulling Qwen via Ollama). The Ollama LLM model can also simply be
re-pulled on the target (`ollama pull qwen3.6:27b-q4`).

---

## 1. What the app is

P1.AIVideo is a **self-hosted, compliance-first pipeline that turns a text brief
into a short AI "talking-head" / reel video** (Romanian-first UI). An operator
creates a *character* (persona), writes or generates a *script*, the system
synthesizes *voice*, generates/uses a *face image*, runs *lip-sync*, edits the
*reel*, runs *QC*, enforces *compliance* (watermark + C2PA + synthetic-person
attestation), and *publishes* a final export.

It is built as a **microservice stack**: a FastAPI backend + Next.js frontend +
a Redis-Streams-driven orchestrator that runs a **DAG of agent stages**, plus a
fleet of **optional, opt-in GPU "model-*" wrapper services** (TTS, image gen,
lip-sync, video gen) that the backend calls over HTTP.

**Tech:** Python 3.11 / FastAPI / SQLAlchemy (async) / Alembic / PostgreSQL /
Redis Streams / MinIO (S3) · Next.js (App Router, TypeScript) · Docker Compose ·
ffmpeg. Auth is JWT + RBAC. The codebase is organized by "Phase N" — historical
increments; phase tags in docstrings tell you *when/why* code was added.

---

## 2. How to run it (the important part)

```bash
make up          # start dev stack (CPU)            → docker/compose.dev.yml
make up-gpu      # dev stack + GPU overlay          → + compose.gpu.yml
make down        # stop
make logs        # tail all services
make ps          # list services
make test        # full pytest suite
```

Default host ports (from `.env`): **backend 8001, frontend 3010, postgres 5433,
redis 6380**, MinIO, and many `model-*` ports (SDXL 8063, FLUX 8064, ComfyUI
8066, MuseTalk 8069, …). The optional Romanian TTS wrapper is profile-gated:
`make docker-tts-ro-build && make docker-tts-ro-up`.

### ⚠️ Critical gotcha — containers BAKE their code
The `backend`, `frontend`, `orchestrator`, agent, and `model-*` images **COPY
their source at build time** (no host source mount for app code in the dev
compose). **Editing a file on disk does NOT change the running container.** After
changing backend/frontend/agent/model code you must rebuild + recreate that
service (e.g. `docker compose -f docker/compose.dev.yml build backend && … up -d
backend`, or the `make docker-tts-ro-*` targets for the TTS wrapper). Tests are
best run in a throwaway container with the repo mounted at `/app` (the image
installs `backend`/`common`/`agents` as editable there), since the host has no
Python test toolchain.

---

## 3. Runtime architecture & the DAG

```
Browser (Next.js :3010)
   │  REST /api/v1/*
   ▼
Backend (FastAPI :8001) ──writes──> PostgreSQL        ──objects──> MinIO (S3)
   │  publishes "job-created"
   ▼
Redis Streams  ──consumed by──>  Orchestrator (run_worker)
                                   │ runs the DAG (pipelines/reel_*.yaml)
                                   ▼ dispatches each stage to an agent
   agents: compliance_officer → scriptwriter → scene_composer → voice →
           face → lipsync → editor → qc → publisher
                                   │ heavy stages call…
                                   ▼
   model-* HTTP wrappers (GPU, opt-in): tts-ro, sdxl/flux/sd35/comfyui,
           sadtalker/wav2lip/musetalk/liveportrait, svd/ltx/animatediff/…
```

**DAG order** (`pipelines/reel_default.yaml`): `policy_gate` (intake compliance)
→ `scriptwriter` → `voice` → `face` → `lipsync` (requires a compliance token) →
`editor` → `qc` → `publisher` (QC-gated final export). Compliance defaults:
watermark + C2PA + compliance-token required.

**Right sidebar logging** is a first-class feature: the frontend `logBus`
(pub/sub) feeds the "Logs" tab; the backend's in-memory `log_buffer` ring
(attached to the **root** logger, so it captures `app.*` AND `security.audit`)
is polled via `GET /api/v1/system/logs/backend` for the "Backend" tab.

---

## 4. Top-level directory map

| Path | What it holds |
| :--- | :--- |
| `backend/` | FastAPI app (`backend/app`), Alembic migrations, packaging. The API + business logic + DB. |
| `frontend/` | Next.js App-Router UI (TypeScript). Operator console. |
| `agents/` | DAG stage handlers + orchestrator + per-stage provider plugins. |
| `common/` | Code shared by backend + agents: enums, exceptions, validation, path safety, shared schemas. |
| `docker/` | One folder per image (`backend`, `frontend`, `agents`, `model-*`) + the three compose files. |
| `pipelines/` | DAG definitions (`reel_default`, `reel_fast`, `reel_news_presenter`, `reel_scenes_only`). |
| `configs/` | Operator config + examples: LLM providers, policies (banned topics), personas, prompts, voices, ComfyUI graph. |
| `workflows/` | ComfyUI JSON graphs (SDXL/PuLID-FLUX/InstantID) + image-analysis prompt. |
| `models/` | **Model weights** (gitignored, mounted read-only): `image/`, `lipsync/`, `tts/`, `video/`, `llm/`, `qwen-gguf/`, etc. |
| `scripts/` | Operator/dev helper scripts (stack start/stop, model downloads, character generation smokes). |
| `tests/` | `integration/` (78 files), `e2e/`, `fixtures/`, shared `conftest.py`. In-memory SQLite. |
| `storage/`, `assets/` | Local artifact storage + sample input assets. |
| `docs/` | `TECHNICAL_ARCHITECTURE.md`, `PROJECT_PLAN.md`, architecture/compliance/runbooks. |
| `Raport claude/`, `Raport_Gemini/` | Audit reports (e.g. R4 logging/security remediation). |
| `Makefile` | All dev/test/ops commands (phase-by-phase test targets). |
| `.env` / `.env.example` | Ports, feature flags, provider base URLs, secrets (not committed). |
| `README.md` (96 KB) | Long-form project narrative / phase history. |

---

## 5. Backend — `backend/app/`

### 5.1 Entry + core (`backend/app/`, `core/`)
| File | Purpose |
| :--- | :--- |
| `main.py` | App factory. Mounts routers, CORS, the request-id+logging middleware (mints `rid`, logs mutating verbs + non-2xx), lifespan (installs log buffer, init DB, bootstraps super-admin, loads secrets into `os.environ`). Sets which routers are public vs `require_active_user` vs `require_super_admin`. |
| `core/config.py` | `Settings` (pydantic-settings) loaded from `.env`: ports, DB URL, auth flags, provider base URLs, feature toggles. |
| `core/db.py` | Async SQLAlchemy engine + sessionmaker; `init_db`, engine reset (tests). |
| `core/deps.py` | FastAPI dependency providers (`get_db_session`). |
| `core/security.py` | **Auth/RBAC guards**: `get_current_user`, `require_active_user`, `require_operator_or_above`, `require_super_admin`. Denials are audited via `security_audit_service`. No-ops when `P1_AUTH_ENABLED=false` (legacy tests). |
| `core/log_buffer.py` | In-memory ring buffer (deque, 1000) attached to the **root** logger + a stdout handler. Feeds the sidebar "Backend" tab. Captures every propagated record incl. `security.audit`. |
| `core/languages.py` | Config-backed language catalog (Phase 11A). |

### 5.2 API routers (`backend/app/api/`) — all under `/api/v1` (jobs also bare)
| File | Endpoint group | Notes |
| :--- | :--- | :--- |
| `auth.py` | `/auth/*` | login, register (always pending/operator/inactive), me, change-password, logout. Fully audited. |
| `users.py` | `/users/*` | user admin (approve/reject/suspend/reactivate/soft-delete). **Super-admin only.** Each transition audited. |
| `audit.py` | `/audit/*` | read the persistent security audit trail. Super-admin only. |
| `secrets.py` | `/secrets/*` | DB-backed API key store (Phase 12X); upsert pushes value into `os.environ`. Super-admin only. delete/list audited. |
| `system.py` | `/system/*` | status/config + `GET /system/logs/backend` (super-admin) for the sidebar; docker control hooks. |
| `jobs.py` | `/jobs` (+ `/api/v1/jobs`) | create (operator+), list (sorted by character), get, PATCH (edit-policy), delete, cancel, retry. Largest router (~1k lines). |
| `uploads.py` | `/uploads/*`, `/jobs/from-inputs` | file intake + create-job-from-uploaded-inputs. |
| `characters.py` | `/characters/*` | persona CRUD, status transitions, image library (generate/accept/reject/set-main), clone, script context. |
| `providers.py` | `/providers/*` | provider catalog per feature (LLM/TTS/video/image/audio) with operator overrides merged. |
| `tts.py` | `/tts/*` | TTS generate (sync + chunked F5 via wrapper). |
| `script.py` | `/script/generate` | scriptwriter (Ollama gated; template always works). |
| `video.py` | `/video/generate` | video-generator contract + categorised errors. |
| `audio_fit.py` | `/audio/fit-check` | audio duration/fit classification. |
| `export.py` | `/export/*` | real ffmpeg final export. |
| `qc.py` | `/qc/*` | on-demand real media QC. |
| `artifacts.py` | `/artifacts/*` | safe artifact content serving. |
| `healthz.py` | `/healthz` | liveness (public). |

### 5.3 Models (`backend/app/models/`) — SQLAlchemy ORM tables
| File | Table / concept |
| :--- | :--- |
| `base.py` | declarative base. |
| `user.py` | users (auth, RBAC roles, registration lifecycle, protected super-admin). |
| `job.py` | jobs (brief, duration, voice/face mode, provider selection, status, character snapshot, scene plan, orientation). |
| `stage_run.py` | one row per DAG stage execution. |
| `artifact.py` | first-class artifacts (audio/image/video/manifest) with paths + checksums. |
| `character.py` | characters/personas + character images + character↔video links. |
| `compliance.py` | append-only compliance events (audit-grade). |
| `security_audit.py` | persistent security audit trail. |
| `feature_provider.py` | operator overrides on top of the code-driven provider registry. |
| `operator_settings.py` | singleton operator settings (language, etc.). |
| `api_secret.py` | DB-backed API secrets. |
| `tts_job.py` | async (chunked) TTS jobs that survive restarts. |

### 5.4 Schemas (`backend/app/schemas/`) — Pydantic request/response
`auth.py` (never exposes `password_hash`), `job.py`, `job_views.py` (read-only
views), `character.py`, `compliance.py`, `providers.py` (provider selection),
`uploads.py`, `api_secret.py`. The frontend's `lib/types.ts` mirrors these.

### 5.5 Services (`backend/app/services/`) — business logic + DB writes
| File | Responsibility |
| :--- | :--- |
| `auth_service.py` | password hashing/policy, JWT encode/decode, super-admin bootstrap, user lookups. |
| `user_service.py` | user lifecycle + state-transition invariants (register/approve/reject/suspend/reactivate/soft-delete). |
| `security_audit_service.py` | structured `security.audit` log + best-effort DB persist; `redact()` for sensitive keys. Never raises into the request. |
| `job_service.py` | create/get/update/delete jobs, `set_job_status`, edit-policy (`compute_edit_policy`), character snapshot. |
| `stage_run_service.py` | DAG stage-run rows. |
| `artifact_service.py` | artifact table writes. |
| `character_service.py` | persona CRUD + lifecycle (editing/active/retired), name/slug uniqueness, voice exclusivity, clone, purge. |
| `character_image_service.py` | character image library: run provider, persist PNG, record row. |
| `character_prompt_builder.py` | build English appearance prompt from profile (Phase 16). |
| `character_script_context.py` | character → LLM script context. |
| `character_lookups.py` | translatable dropdown options for the profile form. |
| `provider_registry.py` | code-driven provider catalog (Phase 6D). |
| `feature_provider_service.py` | DB layer for provider overrides. |
| `secrets_service.py` | secret CRUD + `load_into_env` + provider probes. |
| `image_providers/` | image provider plugins: `base`, `dispatch`, `mock_provider`, `hosted_stub`, `local_wrapper_stub`, `kontext_stub`. |
| `image_workflow_select.py` | VRAM-aware ComfyUI workflow/provider selection. |
| `image_audit.py`, `image_face_score.py` | image compliance events + optional identity-drift scoring. |
| `media_qc.py`, `video_inspection.py` | real media QC + bounded `ffprobe` inspection. |
| `final_export.py` | real ffmpeg final-export. |
| `audio_conversion.py` | ffmpeg audio conversion. |
| `subtitle_service.py` | SRT/VTT subtitle generation. |
| `translator.py` | lightweight RO→EN translation for image prompts. |
| `tts_job_service.py` | run chunked F5 TTS in the background. |
| `upload_service.py` | file-storage helpers for uploads. |
| `queue_publisher.py` | Redis Streams publisher (`publish_job_created`); swappable for fakeredis in tests. |
| `docker_control.py` | on-demand start/stop of GPU model containers via the mounted Docker socket. |

### 5.6 Migrations — `backend/alembic/versions/`
13 ordered migrations `0001_initial` → `0013_tts_jobs` (recovery metadata,
language/subtitles, characters, api secrets, face-locked, scene plan,
orientation, full-body ref, image-role metadata, users/auth, security audit,
tts jobs). `backend/alembic/env.py` wires the async engine.

---

## 6. Agents — `agents/` (DAG stages + orchestrator)

| Path | Role |
| :--- | :--- |
| `orchestrator/orchestrator.py`, `dag.py`, `handlers.py`, `run_worker.py`, `light_idle.py` | DAG runner: consumes Redis events, executes the pipeline YAML, dispatches stages, tracks stage runs. `run_worker.py` is the real Docker-light entrypoint. |
| `compliance_officer/` | `policy_gate` (intake), `pre_lipsync_auth` (mints compliance token), `compliance_token` (mint/verify), `identity_guard`, `export_disclosure_validation` (pre-publish attestation). |
| `scriptwriter/` | `handler.py` + provider plugins (`core/registry` + `providers/`): `template` (default), `ollama` (real), `openai`, `openai_compatible`, `anthropic`, `vllm`, `local_http`. |
| `scene_composer/handler.py` | multi-scene plan composition (Phase 21). |
| `voice/` | `handler.py` + `providers/piper` (real Piper TTS). Provider registry mirrors lipsync. |
| `face/handler.py` | face image stage (Phase 3E/9B). |
| `lipsync/` | `handler.py` + `providers/`: `sadtalker` (+ HTTP `wrapper.py` to the GPU service), `wav2lip`, `musetalk`. Requires a valid compliance token. |
| `editor/handler.py` | edit plan + reel draft (real or metadata-only). |
| `qc/handler.py` | structured QC report from upstream artifacts. |
| `publisher/handler.py` | QC-gated final-export manifest. |

**Provider plugin pattern** (scriptwriter/voice/lipsync): a `core/provider.py`
contract + `core/registry.py` + one folder per backend under `providers/`.

---

## 7. Common — `common/`
| File | Purpose |
| :--- | :--- |
| `enums.py` | shared enums (artifact types, statuses…). |
| `schemas.py` | shared Pydantic schemas. |
| `exceptions.py` | agent-layer exceptions. |
| `path_safety.py` | validate operator-supplied local paths (absolute, no `..`, allowed roots, allowed extensions); logs traversal/outside-root violations. |
| `audio_validation.py` | stdlib-only WAV validation/inspection. |
| `image_validation.py` | stdlib-only image validation + dimensions. |

---

## 8. Frontend — `frontend/` (Next.js App Router, TS)

### 8.1 Pages — `frontend/app/`
| Route | File | Purpose |
| :--- | :--- | :--- |
| `/` | `page.tsx` | public landing (no auth, no shell). |
| `/login`, `/register` | `login/page.tsx`, `register/page.tsx` | auth forms (logBus-instrumented; show/hide password). |
| `/characters`, `/characters/new`, `/characters/[id]` | persona library / create / detail+edit+images. |
| `/jobs`, `/jobs/new`, `/jobs/[jobId]`, `/jobs/[jobId]/edit` | job list / create / detail (progress, artifacts) / edit. |
| `/uploads` | upload inputs. |
| `/settings` | settings panel (API base URL, ports, providers, keys). |
| `/users` | user admin (super-admin). |
| `/technical-help` | help corpus page. |
| `layout.tsx` | root layout: providers, app frame, right sidebar. |

### 8.2 Key components — `frontend/components/`
- **Shell/nav:** `AppFrame`, `LocalizedNav`, `Providers`, `RightSidebar`, `SidebarTabs`.
- **Logging sidebar:** `LogsContext` (subscribes to `logBus`), `LogsPanel` (frontend tab), `BackendLogsPanel` (polls `/system/logs/backend`), `ServicesPanel`, `KeysPanel` (API keys), `SettingsPanel`/`SettingsContext`, `CustomProvidersSection`, `ProvidersSection`, `ProviderTestPanel`, `ProviderStatusBadge`, `BackendStatusBadge`.
- **Jobs:** `CreateJobForm` (the canonical, fully-logBus-instrumented form), `StageTimeline`, `ProgressBar`, `JobRecoveryControls`, `VideoRecoveryHint`, `FinalExportCard`, `QcReportCard`, `ComplianceEvents`, `ArtifactTable`.
- **Characters:** `CharacterForm` (controlled/presentational — CRUD lives in the pages), `CharacterIdentityProfile`, `CharacterImageLibrary`, `CharacterVideoLinks`.
- **Media:** `AuthImage`, `AuthVideo`, `AudioPreview`, `VideoArtifactPreview`, `UploadCard`.
- **Misc:** `StatusBadge`, `LoadingState`, `ErrorMessage`, `LanguageSwitcher`, `Help*` (HelpButton/Context/Hint/Overlay).

### 8.3 Libraries — `frontend/lib/`
| File | Purpose |
| :--- | :--- |
| `api.ts` | typed fetch client (logs network events to logBus, handles 401). |
| `auth.ts` | token + current-user storage (dev: localStorage). |
| `types.ts` | TS mirror of backend Pydantic schemas. |
| `characters.ts`, `users.ts`, `secrets.ts` | per-domain API clients. |
| `settings.ts`, `customProviders.ts` | settings + custom-provider persistence. |
| `log-bus.ts` | module-level pub/sub (`emit`/`subscribe`) — frontend logging backbone. |
| `usePolling.ts`, `format.ts` | polling hook + formatting helpers. |
| `i18n/` | RO/EN dictionaries + formatters + `LanguageContext`. |
| `help/` | RO/EN help corpus (30 topics) + selector + types. |

---

## 9. Docker — `docker/`
- **Compose:** `compose.dev.yml` (CPU dev, all services + profiles), `compose.gpu.yml` (GPU overlay), `compose.prod.yml`.
- **Core service images:** `backend/`, `frontend/`, `agents/` (one image, many agent entrypoints), `models/`.
- **`model-*` wrappers (opt-in GPU HTTP services), each a `Dockerfile + server.py`:**
  - TTS: `model-tts-ro` (F5-TTS Romanian).
  - Image gen: `model-sdxl`, `model-flux`, `model-sd35`, `model-a1111`, `model-comfyui`.
  - Lip-sync / talking-head: `model-sadtalker`, `model-wav2lip`, `model-musetalk`, `model-liveportrait`, `model-echomimic`, `model-hallo`.
  - Video gen: `model-svd`, `model-animatediff`, `model-ltx`, `model-hunyuanvideo`, `model-mochi`.
  - LLM: `model-ollama` (containerised Ollama, alt to host daemon).
- **Infra services:** `postgres`, `redis`, `minio`, `cloudflared` (tunnel).

> Each `model-*/server.py` is a small FastAPI wrapper: lazy-imports the heavy ML
> deps, returns categorised `runtime_missing` / `assets_missing` errors instead
> of fake output, and reads weights from `/models` (mounted read-only).

---

## 10. Config, pipelines, models, scripts
- `pipelines/*.yaml` — DAG templates (`reel_default`, `reel_fast`, `reel_news_presenter`, `reel_scenes_only`).
- `configs/` — `llm/providers.example.yaml`, `policies/banned_topics.example.yaml`, `personas/`, `prompts/`, `voices/`, `comfyui/sdxl_text2img.json` (+ READMEs).
- `workflows/comfyui/*.json` — ComfyUI graphs (SDXL initial, PuLID-FLUX initial/consistent, SDXL+InstantID consistent); `workflows/prompts/character_image_analysis.md`.
- `models/` — weights (gitignored): `image/{sdxl,flux,sd35,controlnet,instantid,insightface}`, `lipsync/{sadtalker,wav2lip,musetalk,liveportrait,echomimic,hallo}`, `tts/{f5tts-ro,piper}`, `video/{svd,ltx,animatediff,hunyuan,mochi}`, `llm`, `qwen-gguf`, `pulid`, `clip`, `vae`, `unet`.
- `scripts/` — `start-stack.sh`/`stop-stack.sh`, `download_instantid_models.sh`, `setup_pulid_flux.sh`, `create_scenario_jobs.py`, `regen_character_photos.py`, `repose_pulid.py`, `generate_seasonal_variations.py`, `smoke_character_generation.py`, `smoke_image_providers.py`.

---

## 11. Tests — `tests/`
- `tests/integration/` — **78 files**, one (or more) per phase (`test_phaseNX_*.py`); plus security/audit ones (`test_phase_auth_rbac.py`, `test_phase_audit_logging.py`, `test_phase12x_secrets.py`).
- `tests/conftest.py` — fixtures; defaults to **in-memory SQLite** (`sqlite+aiosqlite`) and `P1_AUTH_ENABLED=false` (security/audit tests flip it to true in their own fixture).
- `tests/e2e/`, `tests/fixtures/`. Config in `pytest.ini` (`asyncio_mode = auto`).
- Run targeted phases via Makefile (`make phase4a-test`, …) or all via `make test`.
- **Running tests against edited code:** because images bake source, run pytest in a throwaway container of `aivideo-backend:latest` with the repo mounted at `/app`, layering `pytest pytest-asyncio aiosqlite fakeredis httpx`.

---

## 12. Conventions & guardrails
- **Phase tags** (`Phase 12X`, `Phase 23`…) in docstrings mark when/why code was added — keep them when editing nearby code.
- **No fake output:** model wrappers and providers return categorised errors (`runtime_missing`/`assets_missing`/`config_missing`) rather than fabricating media/audio.
- **Security logging:** never log passwords, tokens, secret values, auth headers, cookies, or full payloads. Use `security_audit_service.redact()`; audit denials via `log_access_denied`; frontend logs identifiers only (username/key_name/ids), never secrets.
- **Auth model:** public registration is always `pending`/`operator`/inactive; a protected super-admin is bootstrapped at startup and cannot be modified/deleted.
- **RBAC guards** live in `core/security.py`; routers are mounted public / `require_active_user` / `require_super_admin` in `main.py`.
- **Frontend logBus pattern:** `"<action> submitted"` (info) → `"<action> → <id>"` (success) → `"<action> failed"` (error), with non-sensitive `meta`.
- Migrations are append-only and ordered; add a new `00NN_*.py` rather than editing past ones.
