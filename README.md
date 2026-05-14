# P1.AIVideo

Docker-based multi-agent pipeline that produces short vertical reels (15–60s) featuring a **fully synthetic** white Caucasian human performing lip-synced narration from a text brief.

> **Current status: Phase 4E — Full operator UI + browser CORS fix.**
>
> Closes the loop on the Phase 4D regression where the browser still showed `Failed to fetch` even with Settings → Backend API Base URL set. Adds full operator routes (Jobs list with edit/delete, dedicated Uploads page, dedicated Settings page) and exposes the Docker light-runtime ports as editable operator settings with a copy-ready compose-up command.
>
> **Root cause of "Failed to fetch"** — the backend's default `BACKEND_CORS_ORIGINS=http://localhost:3000` only allowed the standard frontend port. Browser preflight from `http://localhost:3001` returned `400 Disallowed CORS origin` with no `access-control-allow-origin` header, so every API call from the browser failed at the protocol level even though curl on the host worked fine.
>
> **Fix.**
> - `backend/app/core/config.py` default `backend_cors_origins` is now `http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001`. `.env.example` mirrors the new default so a fresh `cp .env.example .env` carries it forward.
> - Verified end-to-end with the dockerized stack on alt ports: preflight OPTIONS from `Origin: http://localhost:3001` now returns `200` with `access-control-allow-origin: http://localhost:3001`; GET / PATCH / DELETE all return 2xx with the credentialed allow-origin header.
>
> **Backend** — Two new endpoints + 12 new tests under `tests/integration/test_phase4e_job_patch_delete.py`:
> - `PATCH /api/v1/jobs/{id}` with `JobUpdateRequest` (every field optional, `extra="forbid"`). Refuses terminal-state edits with `409`. Refuses immutable-field edits (`voice_mode`, `face_mode`, `script_text`, `watermark_required`, `c2pa_required`, `tts_backend`) once the job has progressed past `pending_compliance`. `brief` + `target_duration_seconds` stay editable until terminal.
> - `DELETE /api/v1/jobs/{id}` → 204 / 404. Cascades `stage_runs`, `compliance_events`, `artifacts` via `ON DELETE CASCADE` (SQLite needs `PRAGMA foreign_keys=ON` per connection — added in `app.core.db`).
> - Both endpoints resolve under the legacy `/jobs/*` prefix and the new `/api/v1/jobs/*` alias.
>
> **Frontend** — full operator UX:
> - `/jobs` — full jobs list with paginated polling, status / voice / face / progress / duration / artifact count, and per-row **View / Edit / Delete** actions. Delete uses an inline confirmation row (`Delete? Yes / No`) — no modal library.
> - `/jobs/[jobId]/edit` — editable form scoped to safe fields (brief, duration, script when still pending compliance). Read-only voice / face / tts_backend / watermark / c2pa shown alongside. Submitting calls `PATCH`; inline 4xx detail on validation reject.
> - `/uploads` — three-card grid (text, audio, image) using the same `UploadCard` component as the create-job flow, plus a tab-local "Recent uploads" panel with copy-to-clipboard for each artifact id.
> - `/settings` — full-page version of the right-sidebar Settings panel for operators who want a wider canvas.
> - Top-nav adds `Dashboard / Jobs / New job / Uploads / Settings` (replaces the Phase 4D minimal nav).
>
> **Docker port settings** — `SettingsPanel` now renders a port table for every service in `compose.dev.yml`:
> | Service | Container port | Host port (editable) | Test |
> |---|---|---|---|
> | Backend | 8000 | `backendHostPort` (default 8000) | `GET /healthz` |
> | Frontend | 3000 | `frontendHostPort` | `GET /` |
> | Postgres | 5432 | `postgresHostPort` | via backend `/api/v1/system/status` |
> | Redis | 6379 | `redisHostPort` | via backend (no browser TCP test) |
> | MinIO | 9000 | `minioHostPort` | `GET /minio/health/live` |
>
> Plus dedicated `Test /api/v1/jobs` and `Test /api/v1/stages` buttons.
>
> **Auto-link logic** — editing `backendHostPort` automatically derives `apiBaseUrl = http://localhost:{port}` **unless** the operator has typed into the API URL field (`apiBaseUrlIsCustom=true`). Editing `frontendHostPort` updates the displayed Frontend URL the same way. A single change emits one structured log entry on the bus (`port-edit` vs `url-edit` recorded in meta).
>
> **Compose-up command preview** — Settings shows the exact one-liner derived from the current ports + API URL, with a one-click copy button:
> ```
> BACKEND_PORT=8001 FRONTEND_PORT=3001 POSTGRES_PORT=5433 REDIS_PORT=6380 NEXT_PUBLIC_API_BASE_URL=http://localhost:8001 docker compose -f docker/compose.dev.yml up -d postgres redis backend frontend orchestrator
> ```
>
> **API client diagnostics** — every fetch now logs `url`, `url_source` (`user-override` vs `build-time`), error name, and a hint for the classic "Failed to fetch" CORS case. `getActiveApiBaseUrl()` still reads localStorage on every call.
>
> **Frontend defaults** in Settings — default target duration, default voice mode (TTS or provided_audio), default face-mode-enabled toggle. The create-job form reads them on mount.
>
> **Verification**: `npm run lint` (zero-warnings) ✓, `npm run build` produces 8 routes ✓, `make test` **228 passed / 1 skipped** (was 216 — +12 Phase 4E tests), strict `-W error` pytest sweep also 228/1, dockerized stack on alt ports + new CORS allow-list shows preflight 200 + GET/PATCH/DELETE 2xx end-to-end.
>
> **NOT in Phase 4E**: WebSocket/SSE streaming, persistent backend log shipping, server-side artifact listing endpoint, edit-only-state preflight endpoint, browser-driven Docker control. Logs remain per-tab in-memory operator diagnostics; editing Docker ports in the UI is operator guidance only — restart the stack with the generated env vars to apply.

> **Previous milestone: Phase 4D — Right sidebar (Logs + Settings tabs) and runtime API base URL override.**
>
> Adds a persistent right-side activity sidebar across every page (Dashboard, Job detail, Create job) and a Settings tab that lets the operator override `NEXT_PUBLIC_API_BASE_URL` at runtime — the fix for the "Failed to load jobs → 404" issue when Docker publishes the backend on a non-default port (e.g. `BACKEND_PORT=8001`).
>
> **The 404 root cause + fix**
> - `NEXT_PUBLIC_*` env vars are baked into the JS bundle at `next build`. Phase 4C's frontend image bakes `http://localhost:8000` as the default, so a stack running on `BACKEND_PORT=8001` hits the wrong host port (often a different process entirely).
> - Phase 4D adds a `getActiveApiBaseUrl()` resolver in `frontend/lib/settings.ts` that's called by `lib/api.ts` on every request. It reads `aivideo:settings:v1` from `localStorage` and falls back to the build-time `NEXT_PUBLIC_API_BASE_URL`. Operators flip the Backend API Base URL in **Settings → Backend API Base URL** without rebuilding the image; the next API call uses the new URL.
> - A **Test backend connection** button in Settings calls `GET /api/v1/system/status` and surfaces success/failure inline + on the logs panel.
>
> **Right sidebar** (`frontend/components/RightSidebar.tsx`)
> - Docked to the right edge of `.app-body`; flex-sized so it never overlays main content on desktop. Expanded width 320 px / 260 px on narrow screens, collapsed rail 44 px. Collapsed + active-tab state persisted in `localStorage` (`aivideo:sidebar:v1`).
> - Two tabs (`SidebarTabs`): **Logs** and **Settings**. Collapsed rail still exposes both as clickable vertical labels.
> - Visible on Dashboard, Job detail, and Create job (mounted in `app/layout.tsx`, so every page-level route inherits it).
>
> **Logs tab** (`LogsPanel`)
> - Source-typed entries: `frontend`, `backend`, `api`, `system` × levels `info` / `success` / `warning` / `error`, each colour-coded.
> - Filter by level. Click `+` on an entry to expand structured `meta` (status, duration_ms, error detail, …).
> - Settings drives source toggles + `maxLogEntries` (50 … 5000, default 500). "Clear" button empties the in-memory buffer.
> - **No binary content, no secrets, no raw tokens, no large payloads** — uploads log only `{ kind, ext, size_bytes, filename, artifact_id }`.
>
> **Settings tab** (`SettingsPanel`)
> - Backend API Base URL (with "Test backend connection" button), Frontend URL, Polling interval (1–600 s), Enable/disable auto polling, Show/hide frontend/backend/api/system log sources, Max log entries, Reset to defaults.
> - Persisted to `localStorage` (`aivideo:settings:v1`) under `mergeSettings()` validation so a malformed override falls back to defaults instead of crashing the app.
>
> **Status indicator** (`BackendStatusBadge` — replaces `HeaderStatus`)
> - Lives in the top-right of the header. Polls `/api/v1/system/status` every 15 s. Shows a coloured dot + the active URL + "API reachable / unreachable / Checking…" + last-OK time as a tooltip.
> - When unreachable, surfaces a clear hint: "Open Settings to change the URL". Emits a single `backend unreachable` log when state flips, and a `backend reachable again` on recovery — no flooding.
>
> **API client** (`frontend/lib/api.ts`)
> - Reads `getActiveApiBaseUrl()` on every request — no module-level state that could miss a localStorage update.
> - Emits one structured log per call (`{ method, path, status, duration_ms }`), error level on non-2xx or network failure. Polling endpoints have a `logLabel` so identical entries for `/jobs/:id/progress` etc. don't bloat the log with full UUIDs.
>
> **Job polling** uses `usePolling` with `intervalMs = settings.pollingIntervalSeconds * 1000` and `enabled = hydrated && settings.autoPollingEnabled`. Job detail emits **one** log per status change (not per poll tick) and stops polling once the job is in a terminal status.
>
> **State layer**
> - `SettingsContext` + `LogsContext` + `Providers` wrapper, mounted at the top of `app/layout.tsx`. No Redux/Zustand/SWR — just React context.
> - `lib/log-bus.ts` is a tiny module-level pub/sub so the non-React API client can emit log entries that the LogsContext provider subscribes to.
>
> **Verification**
> - `npm run lint` (zero-warnings via `--max-warnings 0`) and `npm run build` both clean. Bundle sizes: dashboard 1.24 kB → 102 kB first-load; job detail 3.56 kB → 105 kB; new-job 6.85 kB → 94.2 kB (essentially unchanged from Phase 4B).
> - Backend `make test` + strict-warnings `pytest -W error` both stay at **216 passed, 1 skipped**.
> - Docker light smoke (`BACKEND_PORT=8001 FRONTEND_PORT=3001 POSTGRES_PORT=5433 REDIS_PORT=6380 docker compose up`): all five services healthy; frontend `/` returns 200; backend `/healthz` + `/api/v1/jobs` return 200 on 8001; the `aivideo:settings:v1` localStorage key is present in the built bundle, confirming the runtime override path is wired.
>
> **NOT in Phase 4D**: WebSocket/SSE streaming, Tailwind, UI/charting libraries, backend log shipping, persisting logs across reloads, server-side backend status checks. Logs remain a per-tab in-memory operator diagnostic.

> **Previous milestone: Phase 4C — Docker light runtime.**
>
> First real container layer for the project. Until Phase 4C, all three application Dockerfiles were Phase 0 sleep-loop stubs (no source copied, no deps installed). Phase 4C replaces them with actual multi-stage builds and wires the dev compose file for a light, metadata-only run loop. **No GPU, no model weights, no torch / diffusers / transformers / SadTalker / Whisper / SDXL / ffmpeg / OpenCV / moviepy.**
>
> Five services come up via `make docker-light-up`:
> - **`postgres`** + **`redis`** — unchanged from Phase 0.
> - **`backend`** (`aivideo-backend`) — `python:3.12-slim`, multi-stage. Installs `aivideo-common` from `./common`, then `aivideo-backend` from `./backend`. Runs `uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir backend` as non-root user `app`. `HEALTHCHECK` curls `/healthz`. Storage roots `/storage/inputs` and `/storage/artifacts` come from named volumes.
> - **`frontend`** (`aivideo-frontend`) — three-stage `node:20-alpine`. `deps` (`npm ci`), `builder` (`npm run lint && npm run build` with `ARG NEXT_PUBLIC_API_BASE_URL` baked into the bundle), `runner` (`npm run start` as the built-in `node` user). `HEALTHCHECK` via `wget --spider` on `/`.
> - **`orchestrator`** (`aivideo-orchestrator`) — Phase 4C **idle launcher**. Installs `common` + `backend` (temporary Phase 4C coupling — `agents/orchestrator/{dag,handlers}.py` currently `import app.models.*`) + `agents`, then runs `python -m agents.orchestrator.light_idle` which imports every `agents.*` and `common.*` module, logs `ready`, and sleeps. Real worker entrypoint lands in a later phase.
>
> Compose wiring:
> - **GPU agents profile-gated.** `agent-voice`, `agent-face`, `agent-lipsync` now carry `profiles: ["gpu"]`. `model-llm` already had `profiles: ["llm"]`. A default `docker compose up` skips them all — Phase 4C never pulls `nvidia/cuda:…`.
> - **Storage volumes.** Two named volumes (`inputs_data`, `artifacts_data`) are mounted r/w on the backend at `/storage/inputs` and `/storage/artifacts`, and read-only on the orchestrator. Upload + from-inputs flow works end-to-end in Docker.
> - **Backend healthcheck.** `curl /healthz` every 10 s; frontend `depends_on: backend: condition: service_healthy`.
> - **`DATABASE_URL` + `REDIS_URL` overrides** are set on the backend + orchestrator so the in-container connection strings target `postgres:5432` and `redis:6379` (the service names) without depending on the `.env`'s per-component fields.
>
> Tooling:
> - **`.dockerignore`** at the repo root excludes `.venv`, `**/node_modules`, `**/.next`, `**/__pycache__`, `**/*.egg-info`, `.git`, `storage/`, `models/`, and the model-weight extensions (`*.onnx`, `*.safetensors`, `*.pt`, `*.pth`, `*.ckpt`, `*.bin`, `*.gguf`). Build context drops from 521 MB to a few MB.
> - **`frontend/.dockerignore`** for the frontend-stage build context.
> - **`.env.example`** — renamed `NEXT_PUBLIC_API_BASE` → `NEXT_PUBLIC_API_BASE_URL` to match `frontend/lib/api.ts`. Frontend `.env.example` was already correct.
> - **Seven new Make targets**: `docker-config-check`, `docker-light-build`, `docker-light-up`, `docker-light-down`, `docker-light-logs`, `docker-light-smoke`, `docker-light-check` (end-to-end: config → build → up → wait-healthy → smoke → down).
> - **New runbook**: [`docs/runbooks/docker-light-runtime.md`](docs/runbooks/docker-light-runtime.md).
>
> Smoke results (`make docker-light-check`): `GET /healthz`, `GET /api/v1/system/status`, `GET /api/v1/jobs`, `GET /api/v1/stages`, `GET /` on the frontend all return 200 against the dockerized stack. Inside the built images, `python -c "import app.main, app.api.{jobs,uploads,system}, app.core.config"` and `python -c "import agents, agents.orchestrator, …"` resolve cleanly. `make phase4b-test` continues to pass; the strict-warnings pytest sweep (`python -W error -m pytest`) stays clean at 216 passed / 1 skipped.
>
> **Explicitly NOT in Phase 4C**: real video / lip-sync / face generation, SadTalker, Whisper, SDXL, C2PA signing, publishing, GPU image builds, model weight downloads. `docker/agents/Dockerfile.cuda` is unchanged.

> **Previous milestone: Phase 4B — Frontend dashboard + system / config endpoints.**
>
> First-class operator UI in `frontend/` (Next.js 14 App Router, TypeScript, vanilla CSS modules — **no Tailwind, no component libraries, no charting libs**). The UI is **metadata-only**: every screen reads from the FastAPI backend's `/api/v1/*` JSON; no real media plays back, nothing is uploaded externally.
>
> Three pages:
> - **`/`** — Dashboard. Polls `GET /api/v1/jobs` every 5 s and renders one row per job (status, voice/face mode, progress bar, current stage, artifact count, relative-time updated).
> - **`/jobs/new`** — Create-job form. Loads `GET /api/v1/config/ui-options` once for voice/face mode labels, duration bounds, and upload limits. Supports both `tts` (inline `script_text`) and `provided_audio` (upload + reference) flows, with an optional `provided_image` face mode. Submits via `POST /api/v1/jobs/from-inputs`.
> - **`/jobs/[jobId]`** — Live detail. Polls 7 endpoints in parallel every 3 s and renders the job overview, stage timeline, artifact table, compliance events, QC report card, and final-export card.
>
> Backend additions:
> - **`GET /api/v1/stages`** — canonical 11-stage DAG list with human-readable labels and declared order.
> - **`GET /api/v1/artifact-types`** — all 7 `ArtifactType` enum values with labels.
> - **`GET /api/v1/config/ui-options`** — single payload the create-job form consumes: voice modes (with requires_script_text / requires_audio_artifact flags), face modes, TTS backends, duration bounds, upload limits (audio/image max bytes + script max chars + accepted mime types + accepted extensions), and the lists of `JobStatus` / `StageStatus` / `ProviderHealthStatus` / `ArtifactType` values.
> - **`GET /api/v1/system/status`** — small health snapshot (app name + version + phase + scope + server_time + a DB connectivity probe).
> - **`/api/v1/jobs` alias** — the existing `/jobs/*` router is now ALSO mounted at `/api/v1` so the frontend speaks a single `/api/v1/*` prefix. The legacy `/jobs/*` routes stay for backward compatibility with the existing Phase 1–4A tests.
>
> **8 new Phase 4B backend tests** verify the four metadata endpoints' shape (canonical stage ordering, ArtifactType coverage, voice/face/duration/upload limits, system status payload), the `/api/v1/jobs` alias resolves to the same handlers as `/jobs/*` (create + list + detail + progress + timeline + artifacts + compliance-events), the alias 404s on unknown job ids, and a top-level JSON-serializability sweep across all four meta endpoints.
>
> **Frontend zero-warning policy**: `npm run lint` runs `next lint --max-warnings 0`; `npm run build` runs `next build` and must succeed end-to-end. `make phase4b-test` chains the new backend tests with `frontend-check` (lint + build).
>
> **All 216 backend tests + 1 skipped (piper) + frontend lint + build** pass. **No real video / audio / face / lip-sync generation. No Tailwind / component libraries / charting libs added. No SadTalker / Whisper / SDXL / C2PA signing / publishing. No model weights downloaded. No external uploads. No media preview/playback beyond metadata + selected filenames.**

> **Previous milestone: Phase 4A-2 — Upload intake API (text / audio / image) + jobs from-inputs.**
>
> Four new write endpoints under `/api/v1`, all metadata-only in response bodies:
> - `POST /api/v1/uploads/text` — accepts JSON with `script_text` + `title` + `language` + `tone` + `target_duration_seconds`; enforces `SCRIPT_TEXT_MAX_CHARS`; saves a small JSON record under `$UPLOAD_TEXT_ROOT`; registers an orphan `ArtifactType.script` row and returns the `artifact_id` so the future UI can reference it.
> - `POST /api/v1/uploads/audio` — accepts `multipart/form-data` with a `.wav` file; streams to `$UPLOAD_AUDIO_ROOT` with a uuid-derived filename (never echoes the operator's original); enforces `AUDIO_MAX_FILE_SIZE_BYTES`; validates the WAV header via the existing Phase 3D validator; registers an `ArtifactType.audio` row with sample_rate / channels / duration / checksum.
> - `POST /api/v1/uploads/image` — accepts `.png` / `.jpg` / `.jpeg` / `.webp`; streams to `$UPLOAD_IMAGE_ROOT`; enforces `IMAGE_MAX_FILE_SIZE_BYTES`; validates the header via the Phase 3E validator; registers an `ArtifactType.image` row with width / height / checksum.
> - `POST /api/v1/jobs/from-inputs` — dereferences uploaded `*_artifact_id` values back into the `JobCreateRequest` shape (constructing `AudioRef` / `ImageRef` from the artifact's `local_path` + checksum + operator-provided consent flags), then funnels through `job_service.create_job` so every existing compliance / path-safety validator re-runs.
>
> - **`python-multipart`** added to backend deps (FastAPI's required multipart parser; pure-Python, no native deps).
> - **`Artifact.job_id`** is now nullable so upload endpoints can register orphan artifacts before a job exists; subsequent `from-inputs` calls link them via the job's `audio_ref` / `image_ref`. Phase 1 tests still pass — existing rows are always created with a non-null `job_id`.
> - **22 Phase 4A-2 tests** cover: text valid / empty / oversize / unique filenames; audio valid / bad extension / bad header / oversize; image accepted across PNG / JPEG / WebP / rejected extensions / rejected headers; no binary leaks; from-inputs in tts and provided_audio modes (with image), wrong artifact-type rejected, unknown artifact-id rejected, audio_consent_confirmed=False rejected; and a path-traversal-filename test that confirms malicious filenames never escape the upload root.
>
> **No frontend yet. No real video / audio / face / lip-sync generation. No new heavy deps — only python-multipart. No model weights downloaded. No external uploads.**

> **Previous milestone: Phase 4A — Job view API endpoints for the future web UI.**
>
> - Eight read-only FastAPI endpoints under `/jobs`:
>   - `GET /jobs` — paginated list of metadata-only `JobSummary` rows (status, brief, voice/face mode, current_stage, progress_percent, artifact_count).
>   - `GET /jobs/{id}` — existing detail endpoint (Phase 1 contract preserved).
>   - `GET /jobs/{id}/progress` — aggregate (completed / failed / total / current_stage / progress_percent) + per-stage `StageProgress` array, ordered by the canonical 11-stage DAG.
>   - `GET /jobs/{id}/timeline` — `StageTimelineEntry` rows with `started_at` / `completed_at` / `duration_ms` / `error_message` / artifact names / metadata summary.
>   - `GET /jobs/{id}/artifacts` — full `ArtifactResponse` metadata: id, type, uri, mime_type, checksum_sha256, size_bytes, duration_seconds, width/height/sample_rate/channels, local_path, created_at, stage_run_id, metadata_summary. **No binary content** — every value is JSON-native.
>   - `GET /jobs/{id}/compliance-events` — typed compliance audit rows (event_type, decision, reasons, created_at, metadata_summary).
>   - `GET /jobs/{id}/qc-report` — the structured QC report from the QC stage's metadata artifact; 404 when the QC stage hasn't run.
>   - `GET /jobs/{id}/final-export` — the structured `FinalExport` manifest from the publisher's `final_export` artifact; 404 when the publisher hasn't run.
> - **`CANONICAL_DAG_STAGES`** tuple added to `common.enums` so the API and the agent DAG agree about stage order — verified by a test pinning it against `agents.orchestrator.dag.load_stage_order()`.
> - **20 Phase 4A tests** cover: list shape + pagination + ordering, detail fields, progress for both a published and a freshly-created job (0% → 100%), timeline order matches the canonical DAG, artifact metadata-only invariant, compliance event ordering, QC report + final-export 404s when the corresponding stage hasn't run, and a top-level "no binary leaks" sweep that JSON-round-trips every endpoint's response.
>
> **No frontend yet. No real media generation. No new dependencies. No model weights downloaded. No SadTalker / Whisper / SDXL / real lip-sync / face generation implemented.**

> **Previous milestone: Phase 3E — image input validation + face artifact contract.**
> Phase 3D (audio validation + artifact registry) plus a symmetric path for face images:
>
> - **`common/image_validation.py`** — stdlib-only header parsing for **PNG / JPEG / WebP** (VP8 / VP8L / VP8X variants). Returns `(width, height, size, sha256, format)` with no Pillow / OpenCV / imageio / numpy.
> - **`ImageRef`** schema with the same compliance shape as `AudioRef`: both `consent_confirmed` and `synthetic_person_confirmed` must be `true`; path safety against `$PROVIDED_IMAGE_ALLOWED_ROOTS`; only `image/png` / `image/jpeg` / `image/webp` mime types.
> - **`face_mode`** added to `JobCreateRequest` (optional). When set to `"provided_image"`, `image_ref` is required and the face handler validates + emits an `ArtifactRef` with real `width` / `height` / `size_bytes` / `checksum_sha256` / `mime_type`. The DAG runner promotes it into the `artifacts` table just like audio.
> - **`ArtifactType` enum** (`common/enums.py`) — `audio` / `image` / `script` / `video` / `metadata` / `final_export`. Used by the new face artifact registration; existing handlers keep their string literals (no large refactor).
> - **`Artifact` model** gains `width` and `height` columns (None for non-image artifacts).
> - **Compliance event** records `extra={"voice_source": ..., "face_source": "provided_image" | "stub"}`.
>
> **No SDXL. No face generation. No identity / celebrity matching. No SadTalker. No real lip-sync. No Whisper. No torch / torchvision / torchaudio / Pillow / OpenCV / imageio / numpy / diffusers / transformers added. No model weights downloaded. No voice cloning.** See [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) for the full multi-phase plan.

## Hard guarantees

- **Synthetic-only persona.** Faces and voices are generated; no real-person likeness or voice is ever cloned.
- **Mandatory disclosure.** Every output ships with a visible "AI-generated" overlay, a C2PA manifest, and XMP/EXIF flags.
- **Fully local.** Runs in Docker with GPU support; no paid APIs required at any pipeline stage.
- **No surprise downloads.** Model weights are never auto-fetched at build or first run. See [`docs/runbooks/model-management.md`](docs/runbooks/model-management.md).
- **Adapter-pattern model integrations.** Lip-sync (and other model backends) are swappable via env vars — `LIPSYNC_BACKEND=sadtalker` is the v1 default. See [`docs/architecture/lipsync-adapter.md`](docs/architecture/lipsync-adapter.md).

## Prerequisites

- **Docker Engine** (≥ 24) with **Docker Compose v2**.
- **Linux host** (Ubuntu 22.04+ recommended).
- For GPU-enabled services:
  - **NVIDIA proprietary driver** (≥ 550) on the host.
  - **NVIDIA Container Toolkit** so Docker can attach GPUs to containers.
  - Verify with `nvidia-smi` on the host. Setup steps live in [`docs/runbooks/gpu-docker.md`](docs/runbooks/gpu-docker.md).
- **Model weights** live on the host under `./models/` and are bind-mounted into containers. No weights are auto-downloaded; see [`docs/runbooks/model-management.md`](docs/runbooks/model-management.md).
- Copy `.env.example` to `.env` before bringing up the stack.

## Top-level layout

```
docs/        Architecture, compliance, runbooks, full project plan
docker/      Dockerfiles per service + compose overlays
backend/     FastAPI app (jobs, auth, artifacts)
frontend/    Next.js dashboard
agents/      One subfolder per specialist agent (script, voice, face, lipsync, ...)
pipelines/   DAG definitions
models/      Local model weights (gitignored) + model cards
assets/      Licensed/synthetic assets only (fonts, music, b-roll, overlays)
scripts/     CLI helpers (model downloaders, seed scripts, e2e runners)
storage/     Local dev mounts for MinIO + Postgres (gitignored)
tests/       Cross-cutting integration & e2e
configs/     Prompt templates, voice profiles, personas, policy rules
```

## Where to start

1. Read [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) — full technical plan.
2. Read [`docs/architecture/overview.md`](docs/architecture/overview.md) — system architecture.
3. Read [`docs/compliance/policy.md`](docs/compliance/policy.md) — what this system will and will not do.
4. Read [`docs/runbooks/dev-setup.md`](docs/runbooks/dev-setup.md) — Phase 1 quickstart (install Python deps, run the integration test).
5. Read [`docs/runbooks/gpu-docker.md`](docs/runbooks/gpu-docker.md) — host setup for NVIDIA + Docker (only needed once Phase 3 ships).
6. Copy `.env.example` to `.env` and adjust paths.

## Phase 4A-2 scope — current

Implemented on top of Phase 4A:

- **`python-multipart`** added to `backend/pyproject.toml` (pure-Python; FastAPI uses it for `multipart/form-data` parsing).
- **`Artifact.job_id`** made nullable. Upload endpoints register orphan artifacts; `from-inputs` resolves them by id when creating the job (the job's own `audio_ref` / `image_ref` carries the linkage). Phase 1–4A tests unaffected — they all create artifacts with a non-null `job_id`.
- **`backend/app/services/upload_service.py`** — `get_upload_root` (env-driven, resolves+mkdirs), `safe_unique_filename` (uuid4-derived; refuses anything outside `[a-z0-9.]` for the extension), `save_streaming_upload` (chunked write with hard size cap; cleans up partial files on rejection), `compute_sha256`.
- **`backend/app/schemas/uploads.py`** — `UploadTextRequest`/`Response`, `UploadAudioResponse`, `UploadImageResponse`, `JobFromInputsRequest` (with a model-level validator enforcing the voice / face requirement combinations).
- **`backend/app/api/uploads.py`** — two routers:
  - `uploads_router` (prefix `/api/v1/uploads`): `POST /text`, `POST /audio`, `POST /image`.
  - `jobs_v1_router` (prefix `/api/v1/jobs`): `POST /from-inputs`.
- **Config (`.env.example` + `Settings`)** — `UPLOADS_LOCAL_ROOT`, `UPLOAD_AUDIO_ROOT`, `UPLOAD_IMAGE_ROOT`, `UPLOAD_TEXT_ROOT`, `SCRIPT_TEXT_MAX_CHARS=8000`. Default roots sit under `storage/inputs/...` and must overlap with `PROVIDED_AUDIO_ALLOWED_ROOTS` / `PROVIDED_IMAGE_ALLOWED_ROOTS` so `from-inputs` re-validates cleanly.
- **22 Phase 4A-2 tests** in `tests/integration/test_phase4a2_upload_intake_api.py` covering: text valid / empty / oversize / unique filenames; audio valid / non-.wav extension / bad header / oversize; PNG/JPEG/WebP accepted, GIF/non-image rejected, invalid header rejected; no binary in responses; `from-inputs` tts + tts-with-image + provided_audio-with-image happy paths; missing audio in provided_audio rejected; consent=false rejected; wrong artifact_type rejected; unknown artifact_id rejected; malicious filename never escapes the upload root.

Storage safety:

- Filenames are always `uuid4().hex + extension`. The operator's original filename is **not used** for anything — verified by a test that posts `"../../../etc/passwd.wav"` and confirms the saved path stays under the configured root.
- The streaming-save helper closes + unlinks the partial file when the size cap is exceeded, so a malicious large upload never lingers on disk.
- Bad WAV / image bodies are detected after streaming completes — the saved file is scrubbed before the 400 response.

Explicitly **not** in Phase 4A-2:

- **No frontend.**
- **No real video / audio / face generation.** Uploads register metadata only; the existing DAG continues to be metadata-only as well.
- **No external uploads.** Files stay on the local disk under the configured roots.
- **No model weights downloaded.**
- **No auth / RBAC.** Endpoints are open in dev; future phase wires this up.

## Phase 4A scope (still active)

Implemented on top of Phase 3J:

- **`common.enums.CANONICAL_DAG_STAGES`** — `tuple[str, ...]` mirroring `StageName`, in declared order. Backend + agent layer now share one canonical stage list.
- **`backend/app/schemas/job_views.py`** — typed response models for every Phase 4A endpoint: `JobSummary`, `JobProgress`, `StageProgress`, `StageTimelineEntry`, `ArtifactResponse`, `ComplianceEventApiResponse`, `QCReportResponse`, `FinalExportResponse`.
- **`backend/app/api/jobs.py`** — extended with eight read-only endpoints (one of which, `GET /jobs/{id}`, is the Phase 1 detail endpoint, preserved). Each endpoint:
  - returns metadata only (no bytes, no binary blobs);
  - 404s on unknown job id;
  - additionally 404s on the QC / final-export endpoints when the corresponding stage hasn't produced an artifact yet.
- **20 Phase 4A tests** in `tests/integration/test_phase4a_job_api.py`:
  - canonical stage list matches the DAG runner's pipeline order;
  - list shape + pagination + ordering;
  - detail endpoint preserves Phase 1 contract;
  - progress at 0% (pending job) and 100% (published job), with all 11 stages reflected;
  - timeline ordered by canonical DAG;
  - artifacts list carries metadata-only rows with the expected types (`script`, `edit_plan`, `metadata`, `final_export`);
  - compliance events ordered by gate run + carry `voice_source`/`face_source` summary;
  - QC report + final-export endpoints return structured payloads or 404 cleanly;
  - "no binary leaks" sweep JSON-round-trips every endpoint's response.

Explicitly **not** in Phase 4A:

- **No frontend.** This phase is API-only.
- **No real media generation.** Every endpoint exposes existing metadata; no new processing, no new dependencies.
- **No authentication / authorization.** The endpoints are public for now; auth lands in a later phase.
- **No streaming / WebSocket / SSE.** Polling is the assumed pattern.

## Phase 3J scope (still active)

Implemented on top of Phase 3I:

- **`FinalExport`** + `FinalExportStatusType` + `DisclosureStatusType` added to `common.schemas`. The manifest records the would-be publish state, the back-references to source artifacts, and the planned export's mime type — without ever producing a real video file.
- **`agents/publisher/handler.py`** rewritten as the QC gate:
  - Existing rules preserved (`watermark_required` + `c2pa_required` must be true; `export_disclosure_validation` must have run).
  - New: pulls `qc_report` from the QC stage; refuses if missing OR if `extra["qc_passed"]` is False.
  - New: pulls `reel_draft` from the editor stage; refuses if missing.
  - On all checks pass: builds a `FinalExport` manifest, serializes it to JSON, computes a content SHA-256, and emits an `ArtifactType.final_export` artifact (mime `application/json`).
  - Legacy `reel_final.mp4` + `sidecar.json` stubs remain in the output (cross-referencing the manifest by URI + checksum) so a future real-export phase has stable artifact names to drop into.
- **11 Phase 3J tests** in `tests/integration/test_phase3j_publisher_export.py`:
  - 3 happy-path tests (artifact shape, legacy stub preservation, determinism).
  - 5 rejection tests (missing qc_report, missing reel_draft, qc_passed=False, no disclosure gate, watermark_required=False).
  - 1 tmp_path scan confirming no files written to disk.
  - 1 end-to-end DAG test promoting the `final_export` row into the `artifacts` table with the right shape.
  - 1 subprocess-isolated import audit confirming the publisher module pulls in none of `requests`, `httpx`, `aiohttp`, `urllib3`, `boto3`, `botocore`, `aiobotocore`, `minio`, `google.cloud`, `ffmpeg`, `moviepy`, `cv2`, `imageio`, `numpy`, `PIL`, `torch`, `diffusers`, `transformers`, `c2pa`.

Explicitly **not** in Phase 3J:

- **No real video encoding.** Manifest's `export_uri` is still an `s3://` stub.
- **No C2PA signing.** `disclosure_status` is hardcoded to `"pending"` until a future phase wires up `c2patool` (or equivalent).
- **No external uploads.** No social-network APIs, no S3/MinIO client invocation. The publisher's URIs are metadata only.
- **No new dependencies** (no `requests` / `httpx` / `boto3` / `c2pa` / `ffmpeg`).
- **No SadTalker / Whisper / SDXL / real lip-sync / face generation.**
- **No model weights downloaded.**
- **No Docker builds run.**

## Phase 3I scope (still active)

Implemented on top of Phase 3H:

- **`QCDecisionType`**, **`QCCheck`**, and **`QCReport`** added to `common.schemas`.
- **`agents/qc/handler.py`** rewritten:
  - Pulls `edit_plan` + `reel_draft` from the editor stage's output and `script` from the scriptwriter stage's output.
  - Missing required artifacts → `StageRejection` (wiring failure).
  - Runs four named checks:
    - `script_artifact_present` — script ref carries a content checksum.
    - `segments_present` — edit_plan has the three expected types in order: hook, body, cta.
    - `total_duration_matches_target` — segment durations sum (in ms, 1 ms tolerance) to `target_duration_seconds`.
    - `reel_draft_is_stub` — reel_draft is still a Phase 3H stub (s3:// URI, no local_path); a local file triggers a `warn`.
  - Aggregate `passed = True` iff every check is `pass`.
  - Emits a `QCReport` artifact (`ArtifactType.metadata`, mime `application/json`, content SHA-256) with `extra["qc_report"]` carrying the structured report and `extra["qc_passed"]` for cheap downstream filtering.
- **11 Phase 3I tests** in `tests/integration/test_phase3i_qc_report.py`:
  - 2 happy-path tests (artifact shape + checksum + determinism).
  - 3 structural rejection tests (missing edit_plan / reel_draft / script).
  - 4 content-level failure tests (incomplete segments → `segments_present` fails; total mismatch → `total_duration_matches_target` fails; reel_draft with `local_path` → `reel_draft_is_stub` warns; stub reel_draft passes).
  - 1 end-to-end DAG test verifying the metadata artifact lands in the `artifacts` table with the right shape.
  - 1 subprocess-isolated import audit confirming no `ffmpeg` / `ffprobe` / `mediainfo` / `moviepy` / `cv2` / `imageio` / `numpy` / `PIL` / `torch` / `diffusers` / `transformers` / `soundfile` / `librosa` is pulled in.

Explicitly **not** in Phase 3I:

- **No real video / audio QC.** Every check operates on artifact metadata; no file is opened.
- **No `ffmpeg` / `ffprobe` / `mediainfo` / `moviepy` / `OpenCV` / `imageio` / `numpy` / `PIL` added.**
- **No SadTalker / Whisper / SDXL / real lip-sync / face generation.**
- **No model weights downloaded.**
- **No Docker builds run.**

## Phase 3H scope (still active)

Implemented on top of Phase 3G:

- **`ArtifactType.edit_plan`** added to `common.enums` (7 values now).
- **`EditSegment`** and **`EditPlan`** Pydantic schemas in `common.schemas`. Strict validators:
  - per-segment `end - start == duration` (compared in ms, so float ops don't break it);
  - per-plan: sum of segment durations equals `target_duration_seconds`, and segments tile from 0 to the target without gaps or overlaps.
- **Editor handler rewritten** (`agents/editor/handler.py`):
  - Reads the structured script from the scriptwriter stage output (`state.stage_outputs["scriptwriter"].artifacts["script"].extra["structured_script"]`).
  - Allocates `target_duration_seconds` as 20% / 65% / 15% across hook / body / cta. Allocation is done in **milliseconds** so segments sum exactly to the target for any reasonable target duration (30s, 33s, 45s, etc.).
  - Builds an `EditPlan` with three segments, serializes it to JSON, computes a content SHA-256, and emits an `ArtifactType.edit_plan` artifact whose `extra["edit_plan"]` carries the full plan, the source script URI + checksum, and a `no_video_generated: true` flag.
  - Keeps the existing `reel_draft.mp4` stub in the output (downstream QC still checks for it), now cross-referencing the edit plan.
- **14 Phase 3H tests** in `tests/integration/test_phase3h_editor_plan.py`:
  - 5 schema-level tests covering mismatched durations, negative starts, end-before-start, total mismatch, gap-between-segments.
  - 8 editor handler tests: happy path artifact shape, segment percentages exact, reel_draft stub preserved, deterministic same-input output, non-integer target (33s) tiles exactly, missing scriptwriter rejects, missing `structured_script` rejects, no files written to disk.
  - 1 end-to-end DAG test promoting the `edit_plan` row into the `artifacts` table with mime `application/json`, content checksum, and source-script back-references.
  - 1 subprocess-isolated check that importing the editor handler doesn't pull in `ffmpeg` / `moviepy` / `cv2` / `imageio` / `numpy` / `PIL` / `torch` / `diffusers` / `transformers`.

Explicitly **not** in Phase 3H:

- **No real video editing.** Editor remains metadata-only; the URI on the `edit_plan` artifact is an `s3://` stub.
- **No `ffmpeg` / `moviepy` / `OpenCV` / `imageio` / `numpy` / `PIL` added.**
- **No SadTalker / Whisper / SDXL / real lip-sync / face generation.**
- **No model weights downloaded.**
- **No Docker builds run.**

## Phase 3G scope (still active)

Implemented on top of Phase 3F:

- **`agents/scriptwriter/core/provider.py`** — `ScriptProvider` ABC with `provider_name`, `model_name`, `supports_streaming`, `supports_json_mode`, `required_config()`, `healthcheck()`, `generate()`. Plus the structured `ScriptRequest` and `ScriptResult` Pydantic models (hook / body / cta / full_script / estimated_duration_seconds / language / provider / model / prompt_version / metadata).
- **`agents/scriptwriter/core/registry.py`** — `resolve(name)` lazy-imports providers; `known_backends()` advertises the eight names. Unknown backends raise `UnsupportedBackendError`.
- **Template provider** (`agents/scriptwriter/providers/template/provider.py`) — deterministic, dependency-free, produces a structured script from `script_text` (paragraph-split) or from `brief` (placeholder). Default Phase 3G backend.
- **Six stub providers** (`ollama`, `vllm`, `openai_compatible`, `openai`, `anthropic`, `local_http`) — each reads its env config, returns `not_configured` / `not_implemented` from `healthcheck()`, and raises `ProviderNotImplementedError` from `generate()`. Zero external client imports — verified by subprocess audit.
- **DAG handler** wired through the registry. Default backend `template`; configured non-template backends fall back to `template` unless `SCRIPTWRITER_ENABLE_NETWORK_CALLS=true` AND the provider succeeds. Failure of a real provider also falls back, so the DAG keeps moving.
- **Script artifact** carries `ArtifactType.script.value`, a SHA-256 of the serialized structured script, and the `structured_script` dict in `metadata_json` — promoted to the `artifacts` table.
- **Configuration**:
  - `.env.example` block: `SCRIPTWRITER_BACKEND=template`, `SCRIPTWRITER_MODEL=qwen3.6`, `SCRIPTWRITER_FALLBACK_MODEL=qwen3:8b`, `SCRIPTWRITER_ALLOWED_BACKENDS=...`, `SCRIPTWRITER_ENABLE_NETWORK_CALLS=false`, plus per-provider blocks for Ollama / vLLM / OpenAI-compatible / OpenAI / Anthropic / local_http and `LLM_MODEL_REGISTRY_JSON` / `LLM_PROVIDER_CONFIG_PATH`.
  - `configs/llm/providers.example.yaml` — operators copy this and add models/providers without touching code.
- **28 Phase 3G tests** in `tests/integration/test_phase3g_scriptwriter_contracts.py`.

Explicitly **not** in Phase 3G:

- **No real LLM calls.** Every non-template provider's `generate()` raises `ProviderNotImplementedError`.
- **No OpenAI / Anthropic / LangChain / LangGraph / Transformers / Torch / Diffusers added.** Verified twice (Phase 3F + Phase 3G subprocess tests).
- **No HTTP client (`httpx`, `requests`, `aiohttp`) imported at module load.**
- **No API keys required.**
- **No model weights downloaded.**
- **No SadTalker / Whisper / SDXL / real lip-sync / video / face generation.**
- **No Docker builds run.**

## Phase 3F scope (still active)

Structural / test-only cleanup. No new providers, no new features.

- **`agents/pyproject.toml`** — uses `package-dir = {"agents": "."}` plus an enumerated list of all 18 subpackages (`compliance_officer`, `orchestrator`, `scriptwriter`, `voice` + `voice.core` + `voice.providers` + `voice.providers.piper`, `face`, `editor`, `qc`, `publisher`, `lipsync` + `lipsync.core` + `lipsync.providers` + `lipsync.providers.{sadtalker,musetalk,wav2lip}`). Bumped to version `0.3.0`.
- **`tests/conftest.py`** — no longer touches `sys.path`. Only sets test env defaults (`DATABASE_URL`, `APP_ENV`, `LOG_LEVEL`, `COMPLIANCE_SIGNING_KEY`). The previous project-root + backend/ entries are gone.
- **`ArtifactType` enum (`common.enums`)** — six members: `audio`, `image`, `script`, `video`, `metadata`, `final_export`. Voice + face handlers now emit `artifact_type=ArtifactType.<name>.value`. The enum inherits from `str` so legacy code comparing the column to bare strings keeps working.
- **`tests/integration/test_phase3f_packaging_contracts.py`** — 10 packaging-contract tests, four of them subprocess-isolated with `PYTHONPATH` explicitly stripped. Proves the package graph works without any test-only hacks AND that the `agents.*` tree pulls in zero LLM / ML libraries.

Explicitly **not** in Phase 3F:

- **No Scriptwriter / LLM provider implemented.** No `openai`, `langchain`, `langgraph`, `transformers`, `torch`, `diffusers`, `accelerate`, `xformers`, `whisper` added.
- **No SadTalker / lip-sync / SDXL / face-generation / Whisper changes.**
- **No model weights downloaded.**
- **No Docker builds.**
- **No refactor of historical artifact_type literals.** Scriptwriter, lipsync, editor, qc, publisher keep their `"audio"` / `"video"` / `"json"` strings — they're enum-compatible because `ArtifactType` is `str`-derived, and the user spec called the broader refactor "out of scope".

## Phase 3E scope (still active)

Implemented on top of Phase 3D:

- **`common/image_validation.py`** — `validate_and_inspect_image(path, *, mime_type, max_size_bytes=None, min_width=None, min_height=None) -> ImageMetadata`. Hand-rolled header parsers:
  - **PNG**: 8-byte signature + IHDR width/height (24 bytes total).
  - **JPEG**: walks markers until SOF0..SOF15 (excluding DHT/JPG/DAC) and reads height/width from the segment.
  - **WebP**: walks RIFF chunks; supports VP8X (extended), VP8L (lossless), VP8 (lossy) — each variant decoded per its packed format.
- **`ImageRef`** in `common/schemas.py` — `type` (`local_path` | `artifact_uri`), `path`, `mime_type` (`image/png` | `image/jpeg` | `image/webp`), `checksum`, `consent_confirmed` (must be `true`), `synthetic_person_confirmed` (must be `true`). Path safety enforced via `validate_local_image_path`.
- **`face_mode`** + **`image_ref`** added to `JobCreateRequest` / `Job` / `DagState`. `face_mode` is **optional** with no default — jobs that don't opt in keep the existing Phase 2 stub face handler. When explicitly set to `"provided_image"`, `image_ref` is required.
- **Face handler** routes by `face_mode`: stub (default) or `provided_image` (validate + emit populated `ArtifactRef`).
- **`ArtifactType` enum** — `audio` / `image` / `script` / `video` / `metadata` / `final_export`. Used by the new face artifact registration. De-duplication is documented as a future optimization.
- **`Artifact` model** — new `width` and `height` columns.
- **`ArtifactRef`** — gains `mime_type` (top-level), `width`, `height`.
- **`common/path_safety.py`** — refactored to a shared `_validate_local_path` helper used by both audio and image; new `validate_local_image_path` + `get_allowed_image_roots`.
- **Compliance event extra** — `face_source` records `"provided_image"` or `"stub"`.
- **Config** — `PROVIDED_IMAGE_ALLOWED_ROOTS`, `IMAGE_MAX_FILE_SIZE_BYTES` (10 MB default), optional `IMAGE_MIN_WIDTH` / `IMAGE_MIN_HEIGHT`.
- **22 Phase 3E tests** — unit-level coverage of `validate_and_inspect_image` (PNG / JPEG / WebP happy path, missing file, bad header, oversize, unsupported mime, min-dimension enforcement), end-to-end DAG tests (provided_image creates an artifact row with correct width/height; default mode records `face_source="stub"` and creates no image artifact; bad header rejects at face stage; oversize rejects at face stage; metadata-only invariant on artifact rows), and a subprocess-isolated check that no image-ML library is pulled in.

Explicitly **not** in Phase 3E:

- **No SDXL / face generation.**
- **No identity / celebrity / public-figure matching.** The CLIP-NN identity guard documented in `docs/compliance/identity-guard.md` is still deferred. Operator consent flags are the only compliance signal for provided images.
- **No SadTalker / real lip-sync.**
- **No Whisper / LLM script generation.**
- **No torch / torchvision / torchaudio / Pillow / OpenCV / imageio / numpy / diffusers / transformers / accelerate / xformers / gfpgan added.**
- **No model weights downloaded.**
- **No voice cloning.**
- **No artifact deduplication.** A future optimization may dedupe by `checksum_sha256` across jobs; Phase 3E does not.

## Phase 3D scope (still active)

Implemented on top of Phase 3C:

- **`common/audio_validation.py`** — `validate_and_inspect_wav(path, *, mime_type, max_size_bytes=None, allowed_sample_rates=None, allowed_channels=None)` returns an `AudioMetadata` dataclass on success. Stdlib-only.
- **`Artifact` model** (`backend/app/models/artifact.py`) — `artifacts` table with the spec fields; uses `metadata_json` (not `metadata`) to dodge the SQLAlchemy reserved name.
- **`artifact_service`** — `register_artifact` + `register_artifact_ref` + `list_for_job`.
- **Voice handler** — for `voice_mode="provided_audio"` with `type="local_path"`, runs the audio validator and emits a fully-populated `ArtifactRef`. On invalid header / size / sample rate / channels, the stage is rejected (the job moves to `rejected`); no Artifact row is created.
- **DAG runner** — `_record_stage_success` now promotes any `ArtifactRef` with `checksum_sha256` set into the `artifacts` table, linking the row to the originating `stage_run_id`. Stubs are not promoted.
- **`ArtifactRef` schema** — `kind` → `artifact_type`, `sha256` → `checksum_sha256`; added `local_path`, `duration_seconds`, `sample_rate`, `channels`.
- **Config** — `AUDIO_MAX_FILE_SIZE_BYTES` (50 MB default), `AUDIO_ALLOWED_SAMPLE_RATES`, `AUDIO_ALLOWED_CHANNELS`, `ARTIFACTS_LOCAL_ROOT` added.
- **13 Phase 3D tests** — unit-level coverage of `validate_and_inspect_wav` (valid file, missing file, bad header, oversize, unsupported mime, disallowed sample-rate / channels), end-to-end DAG tests (provided_audio creates artifact row with correct extracted metadata; TTS does NOT create an audio artifact; bad WAV rejects at the voice stage; oversize rejects at the voice stage; metadata-only invariant on artifact rows), and a subprocess-isolated check that no audio-ML library is pulled in.

Explicitly **not** in Phase 3D:

- **No Whisper / transcription / alignment.** No `whisper`, `whisperx`, or any speech-to-text library.
- **No SadTalker / real lip-sync changes.**
- **No SDXL / face generation.**
- **No torch / torchvision / torchaudio / diffusers / transformers / accelerate / xformers / gfpgan added.**
- **No ffmpeg / ffprobe** invocations. WAV inspection uses stdlib `wave` exclusively.
- **No model weights downloaded.**
- **No voice cloning.** The schema still refuses any `synthetic_or_owned_voice=False`.
- **No copy / transcode** of provided audio. The file stays where the operator placed it; the registry just records a `file://` URI + metadata.

## Phase 3C scope (still active)

Implemented on top of Phase 3B:

- **`voice_mode`** added to `JobCreateRequest` (`"tts"` default, `"provided_audio"` opt-in).
- **`AudioRef`** (`common/schemas.py`) — typed reference to an operator-supplied `.wav`. Fields: `type` (`local_path` | `artifact_uri`), `path`, `mime_type` (`audio/wav` | `audio/x-wav`), `duration_seconds`, `checksum`, `consent_confirmed`, `synthetic_or_owned_voice`. Validators refuse anything but `true` on both consent flags.
- **Path safety** (`common/path_safety.py`) — `local_path` audio refs must be absolute, free of `..` segments, end in `.wav`, and resolve under one of the directories listed in `$PROVIDED_AUDIO_ALLOWED_ROOTS`. Validation is re-applied at the voice handler as defense-in-depth.
- **Voice handler routes by mode.** `tts` → existing Phase 2 no-op (preserves all previous tests); `provided_audio` → validates + emits `ArtifactRef` with a `file://` URI pointing at the operator's file. Never reads bytes; never transcodes.
- **Compliance audit** — the `policy_gate` event row gains an `extra` JSON column carrying `{"voice_source": "tts" | "provided_audio"}`.
- **Job DB** — `Job` model gains `voice_mode`, `script_text`, `tts_backend`, and `audio_ref` (JSON) columns. `JobResponse` exposes them.
- 13 Phase 3C tests covering schema validation (8 failure modes + happy path), end-to-end DAG runs for both modes, and a subprocess-isolated check that no heavy audio/ML library is pulled in by importing the voice handler.

Explicitly **not** in Phase 3C:

- **No torch / torchvision / torchaudio / diffusers / transformers / accelerate / xformers / gfpgan / SDXL / SadTalker / MuseTalk / Wav2Lip dependencies.**
- **No real lip-sync, no face generation, no SDXL.** All three lip-sync providers + SadTalker are unchanged.
- **No voice cloning.** Hard-coded: the schema refuses `synthetic_or_owned_voice=False`.
- **No external paid APIs.**
- **No DAG wiring of the real Piper provider.** The Phase 3B lazy-import provider remains standalone; the TTS branch of the voice handler is still a no-op stub.
- **No `ffprobe` or real audio validation.** Duration/checksum are recorded verbatim from the operator's declaration; a future phase can add deeper validation.

## Phase 3B (narrow) scope — still active

Implemented on top of Phase 3A:

- **Piper provider's `synthesize()` is now real.** When `piper` is installed and the voice assets are on disk, it loads the voice and writes a WAV via the standard library's `wave` module. The output path is either explicit (`VoiceRequest.output_path`) or a tempfile.
- **Lazy import.** `agents.voice.providers.piper.provider` does **not** import `piper` at module load. The import happens inside `synthesize()` after the assets check. A subprocess-isolated test asserts that importing the provider module does not pull in `piper`, `torch`, `onnxruntime`, `transformers`, or `diffusers`.
- **No auto-download.** Operators place `.onnx` + `.onnx.json` manually under `$PIPER_MODELS_ROOT`. The `ALLOW_MODEL_AUTODOWNLOAD` flag is intentionally not honored at runtime — a future explicit fetch helper will own that.
- **`PiperProvider.healthcheck()`** now reports `piper_runtime_installed` in its `extra` dict so an operator-level healthcheck shows both asset status and runtime availability.
- **5 Phase 3B tests** in `tests/integration/test_phase3b_piper.py` — all pass without `piper` installed; the real-TTS smoke test is skipped unless both `piper` and `$PIPER_TEST_VOICE_ROOT` are provided.

Explicitly **not** in Phase 3B (narrow):

- **No torch / torchvision / torchaudio.**
- **No SadTalker implementation.** SadTalker remains the Phase 3A stub.
- **No real lip-sync.** All three lip-sync providers (SadTalker / MuseTalk / Wav2Lip) still raise `ProviderNotImplementedError` from `synthesize()`.
- **No model weights downloaded.** `piper-tts` itself is not added as a hard dependency in any pyproject.toml.
- **No DAG wiring.** The Phase 2 no-op voice + lipsync DAG handlers are untouched. Wiring the Piper provider into the voice DAG stage is deferred.
- **No external paid APIs.**

## Phase 3A scope (still active)

Implemented on top of Phase 2:

- `LipSyncProvider` and `VoiceProvider` abstract contracts (`agents/lipsync/core/provider.py`, `agents/voice/core/provider.py`) with `required_assets()`, `healthcheck()`, `synthesize()` — plus `validate_compliance_token()` for LipSync.
- `AssetSpec` + `ProviderHealth` + `ProviderHealthStatus` in `common/` so both providers + future ones share the same shape.
- Registries (`agents/lipsync/core/registry.py`, `agents/voice/core/registry.py`) — orchestrator resolves a provider by name (`LIPSYNC_BACKEND`, `TTS_BACKEND`) without importing concrete classes.
- **SadTalker stub** — declares the 5 required checkpoints, resolves `SADTALKER_MODELS_ROOT` (or falls back to `LIPSYNC_MODELS_ROOT/sadtalker`), on-disk healthcheck, fail-fast `synthesize()` (token first, then assets, then `ProviderNotImplementedError`).
- **Piper stub** — declares the configured voice's `.onnx` + `.onnx.json`, resolves `PIPER_MODELS_ROOT` (or `TTS_MODELS_ROOT/piper`), on-disk healthcheck, fail-fast `synthesize()`.
- **MuseTalk + Wav2Lip placeholders** — implement the contract; report `not_implemented`; refuse to run.
- 23-test Phase 3A suite covering: healthcheck states, fail-fast token + asset checks, placeholders, registry resolution, and a subprocess-isolated check that no `torch` / `diffusers` / `transformers` / `sadtalker` / `musetalk` / `piper` imports leak in.

Explicitly **not** in Phase 3A:

- No model weights downloaded. All assets must be manually placed under `./models/` per `docs/runbooks/model-management.md`.
- No `torch` / `torchvision` / `torchaudio` / `diffusers` / `transformers` / SadTalker / MuseTalk / Wav2Lip / GFPGAN / Piper runtime dependencies.
- No real video / audio / face / lip-sync generation. `synthesize()` raises `ProviderNotImplementedError` even when the provider is fully configured.
- No external paid APIs.
- DAG handlers (Phase 2) are still no-ops; the providers exist alongside but are NOT wired into the DAG yet — that wiring is Phase 3B.

## Phase 2 scope (still active)

Implemented on top of Phase 1:

- Shared `common/` package — `JobStatus`, `StageStatus`, `StageName`, `ComplianceDecisionType`, `ArtifactRef`, `StageOutput`, `ComplianceTokenClaims`, `DagState`. Both backend and agents depend on this; agents no longer import backend types (DB access coupling is documented; see [`agents/orchestrator/README.md`](agents/orchestrator/README.md)).
- `StageRun` Postgres model recording every DAG-stage execution (`stage_runs` table).
- `DagRunner` (`agents/orchestrator/dag.py`) — hand-rolled state machine reading the canonical stage order from `pipelines/reel_default.yaml`.
- No-op handlers for every stage (`agents/{scriptwriter,voice,face,lipsync,editor,qc,publisher}/handler.py`).
- Compliance Officer:
  - `pre_lipsync_auth` — mints an HMAC-signed `compliance_token` carrying `synthetic_person_confirmed`, `consent_confirmed`, `watermark_required`, `c2pa_required`, `allowed_lipsync_backend`, `issued_at`, `expires_at`, `phase="phase2_noop"`.
  - `identity_guard` — no-op (real CLIP-NN check deferred to Phase 5).
  - `export_disclosure_validation` — no-op (real OCR + C2PA verify deferred to Phase 5).
- LipSync handler **refuses** to run without a valid `compliance_token`.
- `JobStatus` extended with `published`; a valid job transitions `pending_compliance → accepted → published`.
- Integration test (`tests/integration/test_phase2_noop_dag.py`) verifies the full path, all rejection paths, the token, and the metadata-only invariant.

Explicitly **not** in Phase 2:

- No model weights are downloaded.
- No GPU libraries (torch / diffusers / transformers / SadTalker / MuseTalk / Wav2Lip).
- No real video, audio, face, or lip-sync generation — all artifact references are stub MinIO URIs.
- No external paid APIs.
- No LangGraph — the DAG runner is a 200-line hand-rolled state machine. The handler interface is LangGraph-compatible; Phase 3+ can swap in `langgraph` if branching/retry/parallelism warrants the dep.
- Real SadTalker / MuseTalk / Wav2Lip integration is deferred to Phase 3 behind the existing `LipSyncProvider` adapter contract.

## License

TBD — to be selected at v1 release. Until then, all rights reserved by the project owner.
