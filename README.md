# P1.AIVideo

Docker-based multi-agent pipeline that produces short vertical reels (15–60s) featuring a **fully synthetic** white Caucasian human performing lip-synced narration from a text brief.

> **Current status: Phase 8G — real local generation: Ollama scriptwriter + Piper TTS opt-in.**
>
> **Ollama is now functional.** `OllamaProvider.generate()` (previously
> a stub) runs a real HTTP call to a local Ollama daemon using stdlib
> `urllib.request` (no new pip deps). Live-verified against an Ollama
> daemon at `http://172.17.0.1:11434` (Docker bridge gateway) — returned
> a properly-structured JSON script via `qwen2.5:7b-instruct`. The
> default model stays `qwen3.6` with `qwen3:8b` fallback (per the
> long-standing project invariant). Gated by
> `SCRIPTWRITER_ENABLE_NETWORK_CALLS=true`; off by default. Categorised
> errors on failure: `script_provider_unreachable` (daemon down, no
> route, 5xx), `script_provider_unreachable` with `model_missing:`
> message (model not pulled), `script_generation_failed` for malformed
> responses. Forgiving parser: prefers JSON, falls back to deterministic
> sentence/paragraph segmentation when the model ignores the
> JSON-mode instruction.
>
> **Piper TTS is opt-in.** The light backend stays lean (no
> `piper-tts` / `onnxruntime` by default). New build arg:
> `--build-arg INSTALL_PIPER=true` installs `piper-tts` into the
> backend image. A new `[project.optional-dependencies] tts = ["piper-tts>=1.2"]`
> extra mirrors that for non-Docker venv setups. The categorised 503
> error surface (`tts_runtime_missing` / `tts_assets_missing` /
> `tts_generation_failed`) was already there since Phase 5A; Phase 8G
> fixed a latent bug in the `/api/v1/tts/generate` real-call path
> (missing `job_id`, `Path` instead of `str` in `VoiceRequest`
> construction) that would have surfaced as soon as anyone actually
> installed Piper. The Phase 8A artifact-content endpoint already
> serves the generated WAV.
>
> 14 new Phase 8G Ollama tests (in-process mock daemon — covers JSON
> success, plain-text fallback, model-missing, fallback retry,
> malformed envelope, network-disabled, daemon-unreachable, project
> invariants). 7 new Phase 8G Piper tests (mocked success registers
> a real audio artifact + plays via `/artifacts/{id}/content`).
> Pytest `filterwarnings` now ignores `PytestUnraisableExceptionWarning`
> (CPython 3.14 + asyncio DNS-thread quirk). **501 passed / 10
> skipped** under default and `-W error`. Docker light unchanged
> behavior; 26 jobs preserved through the rebuild.
>
> **Previous milestone: Phase 8F-2 — Test1 right-sidebar provider diagnostics tab.**
>
> New `Test1` tab in the persistent right sidebar (alongside Logs +
> Settings). Operator opens it on any page and probes every provider
> category live: 5 sections (Script LLM / TTS / Video Generator / Audio
> Processor / Image Processor) each listing the catalog rows from
> `GET /api/v1/providers/*` with full metadata (status, backend type,
> locality, default model, GPU/network/weights flags, healthcheck flag,
> docs URL, notes, dropdown-membership). Per-row **Test** button:
> - **LLM** → `POST /api/v1/script/generate` (live preview).
> - **TTS** → `POST /api/v1/tts/generate` (success registers an audio
>   artifact + Test1 renders a play link via the existing
>   `/api/v1/artifacts/<id>/content`).
> - **Video Generator** → readiness-only `GET /api/v1/providers/video_generator/<id>`
>   (never invokes real inference; footnote says so).
> - **Audio Processor / Image Processor** → metadata-only detail
>   endpoint.
>
> Status colour buckets: green (available/configured/ready), yellow
> (not_configured/disabled), red (runtime_missing / gpu_missing /
> assets_missing / error), grey (not_implemented). Each fail surfaces
> a `_ERROR_GUIDE` operator-friendly next-step (e.g. for
> `tts_runtime_missing`: "Run `pip install piper-tts` and rebuild the
> backend"). Every test emits `info` / `success` / `warning` log-bus
> entries (no binary content, no secrets). Frontend-only diff — **zero
> backend changes**, **zero new dependencies**, **no model downloads**,
> **no GPU**. Side-effect Phase 8E touch-up: widened `TTSGenerateResult`
> union to include the success branch that Phase 5A shipped backend-side
> but the frontend never typed. **481 passed / 8 skipped** under
> default and `-W error`. Docker light unchanged; 26 jobs preserved.
>
> **Previous milestone: Phase 8F-1 — strict Create Job contract for
> provider_selection.**
>
> **Phase 8E baseline: operator runtime validation, provider activation
> matrix, log export & scenario job seeding.**
>
> Fixed a regression that blocked Create Job in the browser:
> `JobFromInputsRequest` now accepts `provider_selection` (was rejecting
> with `extra_forbidden`). The upload-intake path forwards the field
> through `JobCreateRequest`, persisting all five Phase 6D categories.
> Six new regression tests pin the contract end-to-end. Log Export now
> ships on the right-sidebar `LogsPanel` — `↓ JSON` (structured: stamp,
> active API base URL, settings snapshot redacted to whitelisted keys,
> full entries) and `↓ TXT` (one line per entry, `timestamp | level |
> source | message`) — both via `Blob` + `ObjectURL`, no external
> library, secrets never serialised. Provider catalog labels cleaned
> up (`OpenAI`, `vLLM`, `OpenAI-compatible API`, `Local HTTP` instead
> of `.title()`-mangled `Openai` / `Vllm` / `Local Http`). Pydantic
> validation errors now humanise on Create Job — `extra_forbidden`
> renders as "Field X is not accepted by this endpoint
> (backend/frontend contract mismatch)" rather than raw JSON. New
> scenario seeder `scripts/create_scenario_jobs.py` + Make targets
> (`scenario-jobs` / `scenario-jobs-check`) — 8 idempotent scenarios
> covering every realistic path (template / mock LLM, Piper TTS, WAV
> upload, MP3→WAV ffmpeg transcode, image validation, SadTalker
> readiness, full provider matrix, future unknown ids). New stop /
> start Make targets (`docker-light-stop` / `docker-light-start`) that
> **never** touch volumes. Phase 6B Alembic was missing from the
> backend image — fixed (`alembic/` + `alembic.ini` now baked) so
> `docker exec aivideo-backend-1 alembic upgrade head` works. Verified
> end-to-end: stopped → started the running stack twice with **20/20
> jobs preserved** (4 pre-existing + 16 scenario-seeded across 2 runs)
> and all four `aivideo_*` volumes intact. **467 passed / 8 skipped**
> under default and `-W error`.
>
> **Previous milestone: Phase 8D — retry / cancel / failure recovery.**
>
> New operator endpoints `POST /api/v1/jobs/{id}/cancel` and
> `POST /api/v1/jobs/{id}/retry`, plus a new `jobs.recovery_metadata`
> JSON column (Alembic migration `0002_phase8d_recovery_metadata` —
> Phase 6B drift guard still green). Cancel flips non-terminal jobs to
> `rejected` with a documented operator-cancellation reason and writes
> a `compliance_events` audit row (`gate=job_cancel`); terminal jobs
> get 409. Retry is allowed only on `failed` / `rejected` jobs —
> bumps `retry_count`, sets `retry_requested_at` + optional
> `retry_stage_name` / `retry_reason`, emits a `gate=job_retry`
> compliance event. Job status is left unchanged on retry (worker
> picks up the marker on the next pass — no DAG re-execution yet,
> documented limitation). Phase 8D explicitly **does not** kill an
> OS process mid-stage; the cancel/retry surface is the metadata
> contract on top of which a future worker-aware control plane lands.
> Frontend gets a new `JobRecoveryControls` card on the Job Detail
> page: enabled-state-aware Cancel + Retry buttons, prompt/confirm
> dialogs, log-bus emission, audit history rendered when
> `recovery_metadata` is non-empty. New runbook:
> `docs/runbooks/failure-recovery.md`. 15 new Phase 8D tests
> (`make phase8d-test`); JobResponse + JobDetail now expose
> `recovery_metadata` (optional, nullable — older clients keep
> working). **461 passed / 8 skipped** under default and `-W error`.
>
> **Previous milestone: Phase 8C — real media QC.**
>
> New operator endpoint `POST /api/v1/qc/inspect`: inspects an on-disk
> video / final_export artifact with deterministic checks +
> ffprobe-driven stream validation, returning a structured report
> (file exists, size > 0, optional checksum match, ffprobe parse,
> video stream present, audio stream present-or-skipped per
> `require_audio`, duration delta with `warn`/`fail` thresholds at
> 1s/5s). New backing service `backend/app/services/media_qc.py`
> exposes `inspect_media_artifact(...)` that **never raises** and
> returns a `MediaQcReport` dataclass with categorised `checks` /
> `warnings` / `failures` lists. Auto-picks `final_export` over
> `video` when both exist for the job. The Phase 3I DAG QC handler
> stays **metadata-only** — Phase 8C is purely additive at the API
> layer. No ML / sync metrics yet (deferred). No GPU. 17 new Phase 8C
> tests (`make phase8c-test`), real-success-path tests skip cleanly
> when ffmpeg / ffprobe aren't on PATH. **446 passed / 8 skipped**
> under default and `-W error`.
>
> **Previous milestone: Phase 8B — real ffmpeg final export.**
>
> New operator endpoint `POST /api/v1/export/finalize`: takes a job's
> video artifact, runs a bounded `ffmpeg` remux (argv list, never a
> shell string; 300s timeout; partial cleanup on failure; ffprobe
> post-validation), and registers an `ArtifactType.final_export` row
> with `mime_type=video/mp4`, real `local_path`, checksum, size,
> duration, and dimensions. Optional `audio_artifact_id` swaps the
> source's audio stream (`-c:v copy -c:a aac`). The endpoint runs
> entirely inside the light backend image — **no GPU**, **no model
> weights**, **no torch**, **no external upload**, and explicitly
> **no watermark burn-in and no C2PA signing** yet
> (`watermark_status="pending"`, `c2pa_status="pending"`,
> `disclosure_status="pending"` baked into the result metadata).
> Categorised error codes (HTTP 200 with structured `status`):
> `video_artifact_missing` / `video_artifact_not_found` /
> `wrong_video_artifact_type` / `video_artifact_no_local_path` /
> `source_outside_allowed_roots` / `ffmpeg_missing` /
> `ffprobe_missing` / `export_failed` / `export_invalid`. The Phase
> 3J publisher's JSON manifest stays untouched. New runbook:
> `docs/runbooks/final-export.md`. New `backend/app/services/final_export.py`
> + the artifact-content serve allow-list now accepts `final_export`
> (real-MP4 variant — the publisher's JSON manifest has no local_path
> so it 404s naturally). 12 new Phase 8B tests
> (`make phase8b-test`), including the real ffmpeg + ffprobe success
> path. **429 passed / 8 skipped** under default and `-W error`.
>
> **Previous milestone: Phase 8A — video artifact preview + safe content serving.**
>
> Generated / uploaded video artifacts are now operator-facing in the
> browser. ``/api/v1/artifacts/{id}/content`` adds ``video`` to its
> serve allow-list and now honours ``ARTIFACTS_LOCAL_ROOT`` as an
> allowed root (the Phase 7D / Phase 8B output area). New optional
> ``?download=true`` query param switches Content-Disposition to
> ``attachment; filename="artifact-<short-id>.mp4"`` — the raw
> on-disk path is **never** echoed in headers. Path traversal, missing
> file, outside-roots, and unknown-id continue to return categorised
> 403 / 404 / 415 the way Phase 4F pinned them.
> New `backend/app/services/video_inspection.py` ships a bounded
> ffprobe helper (argv list — never shell — finite timeout, no torch
> at load) that returns categorised reasons (``ffprobe_missing`` /
> ``invalid_path`` / ``ffprobe_timeout`` / ``ffprobe_failed`` /
> ``parse_failed``) and never raises. Used by the artifact-content
> surface today + by Phase 8B / 8C tomorrow.
> Frontend gets a new ``VideoArtifactPreview`` card on the Job Detail
> page: HTML5 ``<video controls preload="metadata">`` (no external
> player libraries), live size / duration / dimensions / SHA-256 /
> provider badge, and a Download button hitting the same endpoint
> with ``?download=true``. The fallback ``<p>`` inside the ``<video>``
> tag points users at the same download link when their browser can't
> decode the MP4.
> 12 new Phase 8A tests pin the surface (`make phase8a-test`). The
> Phase 4F test that previously pinned ``video → 415`` now pins
> ``edit_plan → 415`` — the gate itself is unchanged. **417 passed /
> 8 skipped** under default and ``-W error``.
>
> **Previous milestone: Phase 7E — pipeline integration for SadTalker (opt-in real inference still gated).**
>
> The DAG's lipsync stage handler is now **provider-aware**.
> ``DagState`` carries ``provider_selection`` (populated from
> ``job.provider_selection``); the handler reads
> ``provider_selection["video_provider_id"]`` and routes:
> - **default** (real-inference flags off) → emits the Phase 2 no-op
>   stub unchanged (every earlier test stays green);
> - **opt-in but un-ready** (``not_configured`` / ``assets_missing`` /
>   ``runtime_missing`` / ``gpu_unavailable``) → raises a categorised
>   ``StageRejection`` — the DAG records the failure cleanly, the job
>   stops, **no phantom artifact** is registered;
> - **opt-in + ready** → calls a module-level ``_attempt_lipsync_inference``
>   hook (tests monkeypatch it; the default body calls
>   ``SadTalkerProvider.generate()`` and surfaces ``video_runtime_missing``
>   when the SadTalker lib isn't installed). On ``completed``, the
>   handler builds a video ``ArtifactRef`` with ``local_path`` +
>   ``checksum_sha256`` + size + duration + dimensions so downstream
>   QC / publisher stages can read it.
> - non-sadtalker providers (``musetalk``, ``wav2lip``) fall through to
>   the no-op stub — their hardened adapters land in later phases
>   mirroring the SadTalker work.
> 11 new Phase 7E tests pin the routing + categorised rejections +
> success-path artifact ref + DAG state population. Downstream
> Phase 3H / 3I / 3J QC/publisher stages remain green. Default
> ``make test`` still never invokes real inference. **405 passed / 8
> skipped** under default and ``-W error``.
>
> **Previous milestone: Phase 7D — SadTalker real inference smoke (opt-in only).**
>
> `SadTalkerProvider.generate()` now ships the real-inference code
> path behind a **seven-gate fence**:
> `SADTALKER_ENABLE_REAL_INFERENCE=true` +
> `RUN_REAL_SADTALKER=1` + weights on disk + torch importable + CUDA
> visible + image path readable + audio path readable. If any gate
> fails, the call short-circuits to a categorised error without
> importing torch / opencv / SadTalker. The default `make test` still
> never invokes real inference — every gate is off by default and the
> real-runtime smoke test (`tests/integration/test_phase7d_sadtalker_inference.py::test_real_sadtalker_smoke_when_explicitly_enabled`)
> auto-skips without `RUN_REAL_SADTALKER_SMOKE=1`. The success path
> (monkey-patched for default CI) registers an `ArtifactType.video` row
> with `mime_type=video/mp4`, checksum, size, optional dimensions, and
> returns `status="completed"` from `/api/v1/video/generate`. Failure
> paths register **no phantom artifact** — the API test pins this
> invariant. Partial-file cleanup on inference exceptions is baked into
> `_attempt_real_inference()`. The existing frontend `ArtifactTable`
> renders video rows without code changes. 7 new Phase 7D tests
> (`make phase7d-test`); Phase 6A / 6D / 7A / 7B / 7C all green. **394
> passed / 8 skipped** (1 new Phase 7D opt-in skip joining the 7 Piper /
> Ollama opt-in skips) under default and `-W error`.
>
> **Previous milestone: Phase 7C — GPU image / runtime for SadTalker readiness (no real inference yet).**
>
> `docker/agents/Dockerfile.cuda` is now a real **readiness image**:
> CUDA 12.4 base + Python 3.11 + ffmpeg + the `common` / `agents`
> wheels, but **no torch and no SadTalker deps** by default. Two opt-in
> build args — `INSTALL_TORCH` (defaults `false`; adds CUDA-12.1 torch
> wheels) and `INSTALL_SADTALKER_DEPS` (Phase 7D placeholder) — let
> operators light up the layers Phase 7D will need. New Make targets
> `make docker-gpu-build` (builds **only** `Dockerfile.cuda`, never
> touches `backend/`/`agents/Dockerfile`) and `make docker-gpu-down`.
> `docker/compose.gpu.yml` extends `agent-lipsync` with SadTalker env
> vars + a **read-only** `:ro` weights mount; both readiness flags
> default off, `ALLOW_MODEL_AUTODOWNLOAD=false`. The default CMD is a
> non-inference readiness probe (`nvidia-smi`, `python --version`,
> torch presence, `inspect_status()`) — never invokes SadTalker. 15
> new Phase 7C tests pin the static + compose invariants
> (`make phase7c-test`); the default light Docker stack still excludes
> all three CUDA agents (`agent-voice` / `agent-face` /
> `agent-lipsync`). The lean image is **~4.5 GB**; with `INSTALL_TORCH=true`
> grows to ~6–7 GB. **388 passed / 7 skipped** under default and
> `-W error`.
>
> **Previous milestone: Phase 7B — SadTalker adapter hardening (no real inference yet).**
>
> First video provider promoted to a *hardened readiness surface* — no
> torch in the default backend, no model downloads, no real generation.
> The SadTalker provider adapter
> (`agents/lipsync/providers/sadtalker/provider.py`) gains
> `inspect_runtime()` / `inspect_assets()` / `inspect_gpu()` /
> `inspect_status()` / `generate()` (stub). All heavy imports are lazy;
> the module loads in the light backend image with **zero** of `torch`,
> `diffusers`, `transformers`, `opencv`, `sadtalker`, `gfpgan` in
> `sys.modules`. `/api/v1/video/generate` for `provider_id="sadtalker"`
> now translates the adapter's readiness into six categorised error
> codes — `provider_not_implemented` (default; Phase 6A-compatible),
> `video_provider_not_configured`, `video_assets_missing`,
> `video_runtime_missing`, `video_gpu_missing`,
> `video_generation_failed` (reserved for Phase 7D) — gated behind
> `SADTALKER_ENABLE_REAL_INFERENCE=true` + `RUN_REAL_SADTALKER=1`.
> Phase 7B intentionally refuses to invoke real inference **even when
> both flags are on** — Phase 7D ships the actual `torch.cuda` call.
> The provider catalog row for sadtalker keeps `status="not_implemented"`
> (Phase 6A invariant) but now exposes live readiness notes +
> `docs_url`. New runbook: `docs/runbooks/sadtalker-runtime.md`. 19 new
> Phase 7B tests pin the surface (`make phase7b-test`); Phase 6A / 6D /
> 7A invariants remain green. **373 passed / 7 skipped** under default
> and `-W error`.
>
> **Previous milestone: Phase 7A — GPU runtime planning.**
>
> Planning + invariants only — no real video, no real lip-sync, no model
> downloads, no torch in the default backend or agents wheel. The
> video-generator catalog (`sadtalker`, `musetalk`, `wav2lip`,
> `liveportrait`, `local_http_video`, `external_video_api`) keeps
> returning metadata-only `not_implemented` from `/api/v1/video/generate`,
> but now the catalog *honestly* advertises `requires_gpu=true` +
> `requires_model_files=true` per provider and the GPU surface is pinned
> by 15 new isolation tests (`make phase7a-test`). The light Docker
> stack still has zero GPU services; the GPU overlay only attaches
> device reservations to three Phase 0 stub agents (`agent-voice`,
> `agent-face`, `agent-lipsync`) gated behind `--profile gpu`. Two new
> Make targets — `make docker-gpu-config-check` and `make docker-gpu-smoke`
> — let operators audit the host without committing to inference. New
> runbooks: `docs/runbooks/gpu-runtime.md` (host pre-flight + invariants)
> and `docs/runbooks/video-providers.md` (candidate comparison + Phase
> 7B first-provider recommendation: **SadTalker adapter hardening, no
> real inference yet** — mirroring the Phase 5A Piper pattern).
> Backend remains GPU-free in every default image.
>
> **Previous milestone: Phase 6B — Alembic migrations.**
>
> Schema changes flow through Alembic now. The FastAPI app does **not** auto-run migrations on startup; operators invoke `make db-upgrade` (or `docker exec aivideo-backend-1 alembic upgrade head` for the Docker light path). `Base.metadata.create_all()` stays in `init_db()` for tests (SQLite in-memory, fresh per fixture); production / dev Postgres deploys go through Alembic instead. +1 dep (`alembic>=1.13`); reuses the existing async drivers via `run_sync()` — no `psycopg2` / `psycopg3` added. Six new Phase 6B smoke tests including a drift guard that fails fast if a model gains a column without a matching migration. New runbook: `docs/runbooks/db-migrations.md`. Backend stays at **306 passed / 4 skipped** under default and `-W error`.

> **Previous milestone: Phase 5A — Real Piper TTS gating.**
>
> Lights up `/api/v1/tts/generate`: when `piper-tts` is installed AND the configured voice (`.onnx` + `.onnx.json`) is on disk under `PIPER_MODELS_ROOT`, the endpoint generates a PCM WAV, validates via the Phase 3D inspector, registers an `ArtifactType.audio` row, and returns metadata. Otherwise it returns a **categorised** 503 — `tts_runtime_missing` / `tts_assets_missing` / `tts_provider_not_configured` / `tts_provider_not_implemented` — so the frontend surfaces an actionable hint. `/api/v1/providers/tts` mirrors the gating with `not_configured` / `configured` / `available`. Reuses Phase 3B PiperProvider; no new dependencies, no model auto-download, no voice cloning. **263 passed / 4 skipped** (Phase 5A real-asset tests cleanly skip without piper-tts).

> **Previous milestone: Phase 4F-3 — Frontend consumes the Phase 4F-2 API backfill.**
>
> Frontend-only follow-up to Phase 4F-2. The UI now uses the new backend contract instead of reconstructing fields client-side. No new dependencies, no Docker change, no boundary shift. Backend stays at **256 passed / 1 skipped**; frontend `lint` + `build` clean across 8 routes.
>
> **Types** (`frontend/lib/types.ts`)
> - `JobSummary` gains optional `qc_passed: boolean | null` and `final_export_available: boolean`.
> - `JobProgress` gains optional `pending_stages`, `completed_stage_names`, `failed_stage_names`, `pending_stage_names`.
> - New `JobDetail extends JobResponse` superset — adds `current_stage`, `progress_percent`, `artifact_count`, `compliance_event_count`, `latest_qc_result`, `final_export_summary`.
> - New `JobFullSummary` for `/summary`: `{ job: JobDetail, progress, timeline, artifacts, compliance_events, qc_report, final_export }`.
> - Old `JobResponse` kept (still returned by `POST /api/v1/jobs`); `JobDetail` is structurally assignable from `JobResponse` so existing call sites keep working.
>
> **API client** (`frontend/lib/api.ts`)
> - `listJobs(params)` accepts optional `status: JobStatus` → sends `?status=…`.
> - `getJob(jobId)` now returns `JobDetail` (backward compatible).
> - New `getJobSummary(jobId)` → `JobFullSummary` (logs as `/api/v1/jobs/:id/summary`).
>
> **Jobs list page** (`/jobs`)
> - New **Status** dropdown at the top: `All`, `Pending compliance`, `Accepted`, `Published`, `Rejected`, `Failed`. Changing it resets pagination implicitly (the loader callback's dependency includes the filter, so the polling restarts) and emits one log entry per filter change.
> - New columns: **QC** (`Passed` / `Failed` / `Pending`) and **Final export** (`Available` / `Not ready`), color-coded.
> - Empty-state message tailors to the active filter.
> - Job count badge ("N jobs") to the right of the filter dropdown.
>
> **Dashboard** (`/`)
> - Same QC + Final-export columns added alongside Status / Progress / Current stage. Surfaces `qc_passed` and `final_export_available` directly from the list payload — no extra round-trips.
>
> **Job detail** (`/jobs/[jobId]`)
> - Primary loader is now a single `GET /api/v1/jobs/{id}/summary` round-trip.
> - **Fallback path:** any non-AbortError / non-404 failure (5xx, CORS, network) silently falls back to the original seven-parallel-fetch loader so the page keeps working against an older backend or during transient flakes. The path used is logged once per path-change (`info` for `/summary`, `warning` for `fallback`) so the operator can see which one is active in the right-sidebar Logs panel.
> - **404** from `/summary` passes straight through to the existing "missing job" error UI (the resource genuinely doesn't exist).
> - Beneath the `ProgressBar`, a new `StageCountsStrip` shows `✓ N completed   ✗ M failed   … K pending   → current_stage`, fed by the Phase 4F-2 flat name lists with a graceful fallback to deriving from `stages[]` if the payload predates the backfill. The `failed` chip dims when `failed_stages == 0`. Hovering each chip shows the relevant stage names as the tooltip.
>
> **Verification**: `npm run lint` → zero warnings; `npm run build` → 8 routes (`/` 3.21 kB / `/jobs` 4.1 kB / `/jobs/[jobId]` 5.84 kB after the new strip — all within the same `87.4 kB shared` budget). Backend `make test` → **256 passed / 1 skipped**; strict `-W error` pytest → identical; `make phase4b-test`, `make phase4f-test`, `make phase4f2-test`, and the new `make phase4f3-test` all pass.
>
> **NOT in Phase 4F-3**: backend changes, Docker changes, dependency changes, new pages. Strictly a frontend consume-the-backfill pass.

> **Previous milestone: Phase 4F-2 — Phase 4A API completeness backfill.**
>
> Purely additive backend work that closes the five spec gaps surfaced in the Phase 4A audit. No frontend change required; no Docker rebuild; no boundary shift. Backend test count goes from **242 → 256 passed / 1 skipped** under both default `pytest` and the strict `-W error` sweep.
>
> **The five deltas**
> 1. **`GET /api/v1/jobs/{id}/summary`** — combined UI payload. One round-trip bundles `job` (the new `JobDetail` shape) + `progress` + `timeline` + `artifacts` + `compliance_events` + `qc_report` (nullable) + `final_export` (nullable). The individual endpoints stay available for incremental polling. 404 on unknown id.
> 2. **`JobSummary.qc_passed: bool | None`** + **`JobSummary.final_export_available: bool`** — derived in the list-endpoint helper from the latest QC `metadata`-typed artifact (`metadata_json["qc_report"]["passed"]`) and the latest `final_export` artifact respectively. Defaults preserve every pre-Phase-4F-2 test (`extra="forbid"`-style `issubset` asserts continue to pass).
> 3. **Aggregate `JobDetail`** — `GET /api/v1/jobs/{id}` now returns a superset of the legacy `JobResponse` shape: every legacy field (id / status / brief / target_duration_seconds / watermark_required / c2pa_required / voice_mode / script_text / tts_backend / audio_ref / face_mode / image_ref / provider_selection / rejection_reason / created_at / updated_at) **plus** `current_stage`, `progress_percent`, `artifact_count`, `compliance_event_count`, `latest_qc_result` (full QC dict or null), `final_export_summary` (six-key headline dict or null). Existing clients reading legacy fields are unaffected.
> 4. **`JobProgress` flat lists** — `pending_stages: int`, `completed_stage_names: list[str]`, `failed_stage_names: list[str]`, `pending_stage_names: list[str]`. Computed from the canonical-DAG-ordered `stages` array; no DB schema change. Defaults preserve backward compat.
> 5. **`GET /api/v1/jobs?status=…`** — typed query param (`JobStatus` enum). Invalid values yield `422` from FastAPI's validator. Pagination + default `ORDER BY created_at DESC` unchanged.
>
> **Helpers**
> Two new internal helpers in `backend/app/api/jobs.py`:
> - `_latest_qc_report_dict(session, job_id) → (dict|None, Artifact|None)` — pulls the most recent QC artifact whose `metadata_json` has a `qc_report` dict.
> - `_latest_final_export(session, job_id) → Artifact | None` — pulls the latest `final_export` artifact whose `metadata_json["final_export"]` is a dict.
> They're reused by `_job_to_summary`, the new `JobDetail` constructor, and the `/summary` endpoint to keep computation in one place.
>
> **Tests** — `tests/integration/test_phase4f2_job_api_backfill.py` has **14 tests**:
> 1. `/summary` combined payload for a published job (job + progress + timeline + qc_report + final_export shape) ✓
> 2. `/summary` 404 on unknown id ✓
> 3. `/summary` for pending job → qc_report + final_export both null ✓
> 4. `JobSummary.qc_passed` + `final_export_available` for both pending and published jobs ✓
> 5. `JobDetail` aggregate fields on a published job ✓
> 6. `JobDetail` aggregate fields on a pending job (zeros + nulls) ✓
> 7. `JobProgress` flat lists for a pending job (`pending_stages=11`, all names in canonical order) ✓
> 8. `JobProgress` flat lists for a published job (`completed_stages=11`) ✓
> 9. `?status=pending_compliance` and `?status=published` filter correctly ✓
> 10. `?status=not_a_real_status` → 422 ✓
> 11. `?status=` combines with `?limit=&offset=` ✓
> 12. None of the new Phase 4F-2 endpoints leak binary content ✓
> 13. None leak the compliance-signing key (defensive sweep) ✓
> 14. Both `/jobs/{id}` legacy prefix AND `/api/v1/jobs/{id}` alias resolve the new shapes ✓
>
> **No frontend changes** — the typed frontend interfaces still describe the legacy subset of the response shape; the new fields are picked up at runtime (TypeScript interfaces don't reject extras). A future frontend pass can expose the new fields directly (e.g. show `qc_passed` and `final_export_available` columns in the dashboard); the contract is in place. No Docker rebuild required.
>
> **NOT in Phase 4F-2**: any new frontend page, any Docker change, any new dependency. Strictly additive backend.

> **Previous milestone: Phase 4F — Provider settings, broader media intake, TTS preview, audio playback.**
>
> Adds the operator-facing controls the pipeline needs *before* any real generation phase lands: a provider catalog with status badges, per-job provider selection dropdowns, a TTS "Generate audio" hook (which intentionally stays a clean `503 tts_provider_not_configured` in light mode), a safe artifact content serving endpoint that powers HTML5 audio + image preview, and a much wider audio upload allow-list (WAV / MP3 / M4A / AAC / FLAC / OGG) with optional ffmpeg-backed conversion to PCM WAV.
>
> **Backend**
> - `Job.provider_selection` — nullable JSON column. Accepted by `JobCreateRequest`, `JobUpdateRequest`, `JobFromInputsRequest`. Whitelisted six-key shape (`script_provider_id`, `script_model`, `tts_provider_id`, `tts_model`, `video_provider_id`, `video_model`); `extra="forbid"` rejects unknown fields with 422.
> - **`GET /api/v1/providers`** (+ `/llm`, `/tts`, `/video-generators`) — metadata-only catalog. LLM list pulled live from `agents.scriptwriter.core.registry.known_backends()`; TTS reports `piper` with `not_configured` until `piper-tts` is installed and `PIPER_MODELS_ROOT` is set; video lists `sadtalker` / `musetalk` / `wav2lip` as `not_implemented`. **No secrets, no API keys, no endpoint URLs returned** — verified by `test_providers_response_carries_no_secret_keys`.
> - **`POST /api/v1/tts/generate`** — accepts `script_text` + `tts_provider_id` + optional `tts_model`/`language`/`output_format`. Always returns `503 { code: "tts_provider_not_configured", message, provider_id }` in light mode. No fake audio is produced; a real provider must be wired into the voice stage.
> - **`GET /api/v1/artifacts/{id}/content`** — streams the file behind an artifact row. Strict guards: must exist, must be `audio`/`image`/`script`, `local_path` must resolve, resolved path must live under one of the configured allowed roots (uploads + provided-asset roots), `..` segments rejected. Sends `FileResponse` with the recorded `mime_type` and `Content-Disposition: inline`.
> - **Audio upload** now accepts `.wav` (canonical), `.mp3`, `.m4a`, `.aac`, `.flac`, `.ogg`. Non-WAV input is transcoded to mono PCM WAV at 22050 Hz via ffmpeg when available; the converted WAV becomes the canonical artifact and the original is kept on disk + recorded in `metadata_json.original_local_path`. Without ffmpeg, non-WAV is stored as-is with `needs_conversion=true` (downstream stages will refuse it).
> - **`ffmpeg`** is installed in `docker/backend/Dockerfile` via Debian apt (pulls `ffprobe` too). Bounded to audio decode/mux by `app/services/audio_conversion.py`. No video pipeline.
>
> **Frontend**
> - **Settings → Providers** — new section listing all known LLM/TTS/video providers with status badges, per-category default-provider dropdown stored in `localStorage`, and a **Test** button for TTS providers (calls `/tts/generate` and surfaces the 503 inline).
> - **Create Job → Providers** — three dropdowns prefilled from Settings defaults. A red-on-yellow warning surfaces when a not-`available` / not-`configured` provider is selected.
> - **Create Job → Voice → Script** — **Generate audio** button next to the textarea. Triggers `/tts/generate`, surfaces "Provider 'piper' is not configured. Install the runtime + place voice assets, then enable in Settings." inline + as a `frontend warn`-level log entry.
> - **AudioPreview** — HTML5 `<audio controls>` rendered immediately after a successful upload or generation. Points at `GET /api/v1/artifacts/{id}/content`. Browser plays MP3 / WAV / OGG / etc. natively.
> - **ImagePreview** — HTML5 `<img>` with the artifact content URL + a `{width}×{height} · {mime}` caption.
> - **Wider audio accept** — `UIOptions.upload_limits.accepted_audio_extensions` now lists `.wav`, `.mp3`, `.m4a`, `.aac`, `.flac`, `.ogg`. The `UploadCard` in the create-job + uploads pages picks up the new list automatically.
> - **Min-quality hints** — inline below each upload control. Audio: target ≥ 22050 Hz, mono/stereo, ≥ 1 s, synthetic or owned. Image: ≥ 512×512 recommended, 1024×1024+ preferred, front-facing, synthetic only.
>
> **Tests**
> - **+14 Phase 4F backend tests** (`tests/integration/test_phase4f_providers_tts_artifacts.py`): providers shape + secret-leak guard, TTS 503 + empty-script 422, artifact content 200 + 404 + 415 + 403 path-outside-roots, MP3 round-trip with ffmpeg (auto-skipped if ffmpeg missing), provider_selection round-trip on create + update, unknown-field 422.
> - **One Phase 4A-2 test relaxed** — MP3 is now an accepted extension; the previous "non-WAV → 400 extension" test was rewritten to assert the policy is "extension outside the Phase 4F allow-list" (uses `.txt` instead).
>
> **Verification**: `npm run lint` (zero-warnings) ✓; `npm run build` 8 routes ✓; backend `make test` → **242 passed / 1 skipped** (216 → 228 → 242 = +14 Phase 4F); strict `-W error` pytest sweep clean. Dockerized smoke confirmed: ffmpeg in container (`ffmpeg 7.1.4`); `/api/v1/providers` returns 8 LLM + 1 TTS + 3 video; `/tts/generate` returns 503 with correct CORS headers; MP3 upload → converted WAV (`pcm_s16le`, 22050 Hz, mono); `/api/v1/artifacts/:id/content` serves the converted WAV (22128 bytes, valid RIFF). New runbook: `docs/runbooks/media-intake-and-providers.md`.
>
> **NOT in Phase 4F**: real TTS synthesis (always 503), real video generation, real lip-sync, browser-driven provider installation ("Add provider package" dialog is Phase 4G), WebSocket/SSE, log shipping, model auto-downloads, GPU work.

> **Previous milestone: Phase 4E — Full operator UI + browser CORS fix.**
>
> Closes the loop on the Phase 4D regression where the browser still showed `Failed to fetch` even with Settings → Backend API Base URL set. Adds full operator routes (Jobs list with edit/delete, dedicated Uploads page, dedicated Settings page) and exposes the Docker light-runtime ports as editable operator settings with a copy-ready compose-up command.
>
> **Root cause of "Failed to fetch"** — the backend's default `BACKEND_CORS_ORIGINS=http://localhost:3000` only allowed the standard frontend port. Browser preflight from `http://localhost:3010` returned `400 Disallowed CORS origin` with no `access-control-allow-origin` header, so every API call from the browser failed at the protocol level even though curl on the host worked fine.
>
> **Fix.**
> - `backend/app/core/config.py` default `backend_cors_origins` is now `http://localhost:3000,http://localhost:3010,http://127.0.0.1:3000,http://127.0.0.1:3010`. `.env.example` mirrors the new default so a fresh `cp .env.example .env` carries it forward.
> - Verified end-to-end with the dockerized stack on alt ports: preflight OPTIONS from `Origin: http://localhost:3010` now returns `200` with `access-control-allow-origin: http://localhost:3010`; GET / PATCH / DELETE all return 2xx with the credentialed allow-origin header.
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
> BACKEND_PORT=8001 FRONTEND_PORT=3010 POSTGRES_PORT=5433 REDIS_PORT=6380 NEXT_PUBLIC_API_BASE_URL=http://localhost:8001 docker compose -f docker/compose.dev.yml up -d postgres redis backend frontend orchestrator
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
> - Docker light smoke (`BACKEND_PORT=8001 FRONTEND_PORT=3010 POSTGRES_PORT=5433 REDIS_PORT=6380 docker compose up`): all five services healthy; frontend `/` returns 200; backend `/healthz` + `/api/v1/jobs` return 200 on 8001; the `aivideo:settings:v1` localStorage key is present in the built bundle, confirming the runtime override path is wired.
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

## Help & documentation maintenance rule

**Any change that adds, removes, or modifies a user-visible surface must update
the help system, both translation dictionaries (ro + en), and the relevant
runbook in the same PR.** "User-visible" here means: a UI page or control, a
backend API endpoint, a provider, a runtime status, a categorised error code,
an operator setting, or a Docker profile.

Bilingual checklist (Phase 11A re-do + Phase 11A-FIX):

> **Permanent rule:** every user-visible UI / API / provider / runtime /
> error / help change must update the EN and RO dictionaries and Help
> topics. A change is *incomplete* if it introduces visible text without
> i18n keys. The Phase 11A-FIX test suite
> (`test_phase11a_no_hardcoded_english.py`) scans every `frontend/app/`
> and `frontend/components/` `.tsx` file for the known regression
> phrases and refuses `humanize()` imports in mainline visible
> components.

- New UI label → add the key in **both** `frontend/lib/i18n/dictionaries/en.ts` and `ro.ts`.
- New button or form section → wire `useT()` + add a `<HelpHint slug="…"/>`.
- New API endpoint → update `docs/runbooks/api-surface.md`.
- New provider → add a help topic in **both** `frontend/lib/help/dictionaries/en.ts` and `ro.ts`, plus its error codes.
- New error code → add it to `errors.*` in both UI dictionaries **and** mention it in the `errors-glossary` help topic.
- New setting → add it to `settings.*` in both UI dictionaries, document in the `settings` help topic.
- New status / stage / artifact type / voice mode / face mode / provider status → add to `statuses.*` / `stages.*` / `artifactTypes.*` / `voiceModes.*` / `faceModes.*` / `providerStatuses.*` in **both** UI dictionaries. Use the matching `t<Enum>` helper from `frontend/lib/i18n/formatters.ts` — never `humanize()`.
- New relative-time display → use `formatRelativeLocalized(t, iso)`, never `formatRelative(iso)`.
- New backend Pydantic validation message → add a mapping in `localizeApiDetail` and a `validation.*` key in both dictionaries.

Concretely, every PR that touches one of those must also update **at least
one** of these:

- `docs/runbooks/api-surface.md` — backend HTTP contract (API row)
- `docs/runbooks/ui-api-parity.md` — UI ↔ API mapping (matrix row)
- `frontend/lib/help/content.ts` — in-app Help overlay article(s)
- `frontend/lib/api.ts` + `frontend/lib/types.ts` — typed client + TS types
- the relevant runtime runbook in `docs/runbooks/` (e.g. `sadtalker-runtime.md`)

The checklist for which doc to update per change type lives in
[`docs/runbooks/contribution-rules.md`](docs/runbooks/contribution-rules.md).

Phase 10C ships three lightweight tests that enforce this:

```bash
pytest -q tests/integration/test_phase10c_api_surface.py
pytest -q tests/integration/test_phase10c_ui_api_parity.py
pytest -q tests/integration/test_phase10c_help_coverage.py
```

A PR is incomplete if any of these fail. Fix the docs (almost never the test).

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
