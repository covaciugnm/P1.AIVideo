# Developer Setup

How to bring up a P1.AIVideo dev environment on a Linux workstation. The first half of this runbook covers what works **today (Phase 1)**; the second half describes the full stack that lights up in later phases.

## Phases 1 → 3B quickstart (no Docker, no model weights required)

Phases 1, 2, 3A, and 3B (narrow) are all runnable without GPU and without model weights. Phase 3B's real-TTS path activates only when you explicitly opt in by installing `piper-tts` (a CPU-only Python package; no torch). The test suite passes whether or not Piper is installed.

```bash
python -m venv .venv
source .venv/bin/activate

# Install order matters: `common` is a dependency of `backend` and `agents`.
pip install -e ./common
pip install -e ./backend[dev]
pip install -e ./agents[dev]

# Run the integration tests (SQLite in-memory + fakeredis; no model weights)
make phase1-test
make phase2-test
make phase3a-test
make phase3b-test
make phase3c-test
make phase3d-test
make phase3e-test
make phase3f-test
make phase3g-test
make phase3h-test
make phase3i-test
make phase3j-test
make phase4a-test
make phase4a2-test
make phase4b-test       # backend meta endpoints + frontend lint+build
# or together:
make test
```

> Phase 3F made packaging strict: the test suite imports every project module through the **installed** editable packages, not via a project-root `sys.path` hack. If `pytest` fails with `ModuleNotFoundError: No module named 'app'` (or `agents`, or `common`), re-run the three `pip install -e` commands above.

### Optional: enable the real Piper TTS path (Phase 3B)

```bash
# Add Piper to the venv (CPU-only Python package; no torch).
pip install piper-tts

# Place a voice manually under $PIPER_MODELS_ROOT, e.g.:
#   ./models/tts/piper/en_US-amy-medium.onnx
#   ./models/tts/piper/en_US-amy-medium.onnx.json
# Download from the official Piper voices index per its license terms.
# (We do not auto-download.)

# Point the integration test at the voice directory and re-run:
export PIPER_TEST_VOICE_ROOT=$(pwd)/models/tts/piper
make phase3b-test
```

You can also run the API locally without Docker:

```bash
# in another shell, with the venv activated
uvicorn app.main:app --reload --app-dir backend
# then
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
        "brief": "Three calming bedtime habits for better sleep.",
        "synthetic_person_confirmed": true,
        "consent_confirmed": true,
        "target_duration_seconds": 30,
        "watermark_required": true,
        "c2pa_required": true
      }'
```

Note: when running the API directly (not via `pytest`) you'll want a real Postgres + Redis. The simplest way to get those is `make up` (see below).

### Frontend (Phase 4B)

Next.js 14 App Router + TypeScript + vanilla CSS modules. No Tailwind, no
component libraries.

```bash
# Install dependencies (first time only — ~330 packages).
make frontend-install

# Run the dev server on http://localhost:3000 (talks to the backend at
# http://localhost:8000 via /api/v1/* by default).
cd frontend && npm run dev

# Or run the same checks CI does:
make frontend-check    # next lint --max-warnings 0 + next build
```

To point the frontend at a non-default backend URL, copy `frontend/.env.example`
to `frontend/.env.local` and edit `NEXT_PUBLIC_API_BASE_URL`. `.env.local` is
the **build-time** default — the right sidebar's **Settings → Backend API
Base URL** is the **runtime** override stored in localStorage and applied
on every API call (use this when Docker publishes the backend on a
non-default port without a rebuild).

### Phase 8G: real local generation — Ollama scriptwriter + Piper TTS opt-in

Ollama scriptwriter now actually generates. Piper TTS install is now
a one-flag opt-in.

```bash
# Ollama — needs a daemon reachable from the backend container.
# From the alt-port Docker stack, that's the Docker bridge gateway:
docker exec aivideo-backend-1 sh -c '
  SCRIPTWRITER_ENABLE_NETWORK_CALLS=true \
  OLLAMA_BASE_URL=http://172.17.0.1:11434 \
  OLLAMA_MODEL=qwen2.5:7b-instruct \
  python -c "import asyncio,uuid;
from agents.scriptwriter.providers.ollama.provider import OllamaProvider
from agents.scriptwriter.core.provider import ScriptRequest
async def m():
  p=OllamaProvider()
  r=await p.generate(ScriptRequest(job_id=uuid.uuid4(), brief=\"reel about local bakery\", target_duration_seconds=30, language=\"en\"))
  print(r.hook); print(r.body); print(r.cta)
asyncio.run(m())"
'

# Piper — opt in at build time.
INSTALL_PIPER=true \
  BACKEND_PORT=8001 FRONTEND_PORT=3001 POSTGRES_PORT=5433 \
  NEXT_PUBLIC_API_BASE_URL=http://localhost:8001 \
  docker compose -f docker/compose.dev.yml build backend

# Place voice .onnx + .onnx.json under host:
#   ./models/tts/piper/en_US-amy-medium.onnx
#   ./models/tts/piper/en_US-amy-medium.onnx.json
# (operator-managed; no auto-download)

make phase8g-test                # 21 mocked tests (14 Ollama + 7 Piper) + 2 opt-in skips
```

See [`ollama-scriptwriter.md`](ollama-scriptwriter.md) and
[`piper-runtime.md`](piper-runtime.md) for the full setup matrix.

### Phase 8F-2: Test1 right-sidebar provider diagnostics

Operator-facing diagnostics surface. Open the right sidebar (visible on
every page) → click **Test1**. The panel groups all five Phase 6D
provider categories into sections, lists every provider with status +
metadata + flags, and exposes a **Test** button per row. The buttons
hit only the safe / preview / readiness endpoints — video providers
stay metadata-only, with a footnote stating "Real video generation is
not run from Test1".

```
Status dot colour:
  green   → available / configured / ready
  yellow  → not_configured / disabled
  red     → runtime_missing / gpu_missing / assets_missing / error
  grey    → not_implemented (registry placeholder)
```

Every Test action emits a log-bus entry. Tests don't change DB rows.
Frontend-only feature.

See [`provider-registry.md`](provider-registry.md) for the underlying
catalog. No new backend tests — the Phase 6D / 7B / 7D suites already
pin the endpoints Test1 hits.

### Phase 8E: operator runtime + scenario job seeding

Fixes the browser `extra_forbidden` regression on Create Job; adds
JSON / TXT log export buttons to the right-sidebar logs; cleans
provider labels; humanises Pydantic validation errors. Scenario
seeder seeds 8 realistic jobs against the running stack:

```bash
# Seed 8 scenario jobs (idempotent — appends each run)
make scenario-jobs

# Confirm they appear in the job list
make scenario-jobs-check

# Stop / start preserving every volume
make docker-light-stop
make docker-light-start

# If you carry an old Postgres volume from before Phase 6B, stamp the
# initial migration once and upgrade:
docker exec -w /app/backend aivideo-backend-1 alembic stamp 0001_initial
docker exec -w /app/backend aivideo-backend-1 alembic upgrade head

make phase8e-test                # 6 regression tests for the contract
```

See [`scenario-jobs.md`](scenario-jobs.md) for the scenario matrix.

### Phase 8D: retry / cancel / failure recovery

New operator endpoints `POST /api/v1/jobs/{id}/cancel` and
`POST /api/v1/jobs/{id}/retry`, backed by a new `jobs.recovery_metadata`
JSON column (Alembic migration `0002_phase8d_recovery_metadata`).

```bash
make phase8d-test                # 15 invariants
```

See [`failure-recovery.md`](failure-recovery.md) for the endpoint
contracts, recovery-metadata fields, audit-event mapping, and the
known limitations (no OS process kill yet).

### Phase 8C: real media QC

New operator endpoint `POST /api/v1/qc/inspect` runs deterministic
file checks + ffprobe inspection on a video / final_export artifact.
Returns a structured report (checks list, warnings, failures) without
mutating the Phase 3I DAG QC manifest. No ML / sync metrics yet.

```bash
make phase8c-test                # 17 invariants (real-success paths need ffmpeg+ffprobe)
```

See [`final-export.md`](final-export.md) and the request body shape in
`backend/app/api/qc.py`.

### Phase 8B: real ffmpeg final export

New operator endpoint `POST /api/v1/export/finalize` packages a job's
video artifact into a clean MP4 `final_export` row. No GPU, no model
weights, no watermark burn-in, no C2PA signing — those statuses are
recorded as `pending` in the result metadata.

```bash
make phase8b-test                # 12 invariants (real-export path needs ffmpeg+ffprobe)
```

See [`final-export.md`](final-export.md) for the categorised error
table, safety contract, and the `audio_artifact_id` mux path.

### Phase 8A: video artifact preview + safe content serving

Generated MP4s are operator-facing in the browser. The Job Detail page
gets a Video preview card with HTML5 ``<video controls>``, live
metadata, and a Download button. ``/api/v1/artifacts/{id}/content``
now serves ``artifact_type=video`` and accepts ``?download=true`` for
the attachment Content-Disposition.

```bash
make phase8a-test                # 12 invariants
```

The Phase 8B / 8C final-export + real-media-QC phases reuse the
bounded ffprobe helper at ``backend/app/services/video_inspection.py``.

### Phase 7E: lipsync DAG stage integration (opt-in real inference still gated)

The DAG's lipsync stage handler is now provider-aware:
``state.provider_selection["video_provider_id"]`` controls which video
provider runs. When the provider is SadTalker and all real-inference
gates are satisfied, the handler delegates to a monkey-patchable hook
(``_attempt_lipsync_inference``) that calls
``SadTalkerProvider.generate()`` and wraps the result in a video
``ArtifactRef``. Otherwise the Phase 2 no-op stub is preserved, or a
categorised ``StageRejection`` fires when the operator opted in but a
gate is missing.

```bash
make phase7e-test                # 11 invariants
```

### Phase 7D: SadTalker real inference (opt-in only)

`SadTalkerProvider.generate()` now invokes real inference behind a
**seven-gate fence**. Default `make test` never reaches the real path;
the opt-in smoke test auto-skips without `RUN_REAL_SADTALKER_SMOKE=1`.

```bash
make phase7d-test                # 6 passed + 1 opt-in skip by default

# Real end-to-end smoke (requires GPU host + weights + heavy GPU image):
RUN_REAL_SADTALKER_SMOKE=1 SADTALKER_ENABLE_REAL_INFERENCE=true \
RUN_REAL_SADTALKER=1 SADTALKER_MODELS_ROOT=/path/to/weights \
  make phase7d-test
```

See [`sadtalker-runtime.md`](sadtalker-runtime.md) §4b for the
seven-gate table and the success-path API response shape.

### Phase 7B: SadTalker adapter hardening (no real inference yet)

First hardened video provider. The adapter (`agents/lipsync/providers/sadtalker/provider.py`)
ships `inspect_runtime()` / `inspect_assets()` / `inspect_gpu()` /
`inspect_status()` / `generate()` (stub). `/api/v1/video/generate` for
`provider_id="sadtalker"` now returns six categorised `error_code`s.

```bash
make phase7b-test                # 19 invariants
```

See [`sadtalker-runtime.md`](sadtalker-runtime.md) for the env-var gate,
the error-code table, and the no-auto-download policy.

### Phase 7A: GPU runtime planning (no real inference yet)

Planning + invariants only. The default light stack stays GPU-free; the
GPU overlay attaches `nvidia` device reservations to three CUDA agents
that remain Phase 0 stubs.

```bash
make phase7a-test                # 15 isolation invariants
make docker-gpu-config-check     # compose.dev + compose.gpu merge cleanly
make docker-gpu-smoke            # nvidia-smi inside CUDA container (skips on CPU host)
```

See [`gpu-runtime.md`](gpu-runtime.md) for the host pre-flight + invariants
and [`video-providers.md`](video-providers.md) for the candidate
comparison + Phase 7B first-provider recommendation.

### Phase 6D: multi-provider registry + custom providers

Five operator-facing categories: `llm` / `tts` / `video_generator` /
`audio_processor` / `image_processor`. The Settings panel ships an
"Add custom provider" UI (metadata-only, localStorage-backed). See
[`provider-registry.md`](provider-registry.md) for the architecture +
the custom-provider workflow.

```bash
make phase6d-test      # 21 tests pinning the catalog + selection contract
```

### Phase 6C: real runtime readiness (Piper + Ollama)

Pre-GPU dry run for the two CPU-local runtimes. Neither is installed by
default — both are operator-managed. Pick a path:

```bash
# Verify the readiness surface (no real runtime needed):
make phase6c-test                # 12 passed / 3 conditional skips

# Curl the live readiness surface against a running backend:
make docker-light-up
make runtime-readiness-check     # full curl matrix
make docker-light-down

# Enable real generation:
#   1. See docs/runbooks/piper-runtime.md for Piper TTS setup
#   2. See docs/runbooks/ollama-scriptwriter.md for qwen3.6 / Ollama setup

# Opt-in real-runtime tests (require manual setup):
RUN_REAL_PIPER_SMOKE=1 PIPER_MODELS_ROOT=… pytest tests/integration/test_phase6c_runtime_readiness.py
RUN_REAL_OLLAMA_SMOKE=1 SCRIPTWRITER_ENABLE_NETWORK_CALLS=true pytest tests/integration/test_phase6c_runtime_readiness.py
```

The two new runbooks
[`piper-runtime.md`](piper-runtime.md) and
[`ollama-scriptwriter.md`](ollama-scriptwriter.md) walk each setup
end-to-end including provider-status interpretation, the 503 code
dictionary, and Docker integration notes.

### Phase 6B: database migrations

Schema changes flow through Alembic now. Quick reference:

```bash
make db-current                # show the DB's current revision
make db-history                # list migrations
make db-upgrade                # apply migrations up to head
make db-downgrade              # revert one
make db-migrate MSG="add foo"  # after a model change → autogenerated migration
```

See [`db-migrations.md`](db-migrations.md) for the full workflow, the
Docker light path, the drift-guard test, and the deploy SQL-export
recipe.

### Phase 4F-3: frontend consumes the Phase 4F-2 backfill

Frontend-only. Run `make phase4f3-test` (frontend lint + build + Phase 4F-2
backend tests). The Jobs list now shows QC and Final-export columns and a
Status filter dropdown that wires straight into `?status=…`. The detail
page now uses `/api/v1/jobs/:id/summary` as the primary loader with a
transparent fallback to the legacy seven-fetch path; the chosen path is
logged in the right-sidebar Logs panel.

### Phase 4F-2: extra job-view fields + status filter

Additive only. `GET /api/v1/jobs` now accepts `?status=<JobStatus>` (returns
422 on invalid values). `GET /api/v1/jobs/{id}` now returns a superset
`JobDetail` shape (legacy fields preserved + `current_stage`,
`progress_percent`, `artifact_count`, `compliance_event_count`,
`latest_qc_result`, `final_export_summary`). `GET /api/v1/jobs/{id}/summary`
bundles all seven detail-page endpoints into one response. The list payload
now carries `qc_passed` and `final_export_available` per row, and the
progress payload now carries `pending_stages` + the three flat
`{completed,failed,pending}_stage_names` lists. Run `make phase4f2-test` for
the 14 new tests.

### Phase 4F: ffmpeg for audio conversion

Audio uploads now accept WAV / MP3 / M4A / AAC / FLAC / OGG. Non-WAV input
is transcoded to PCM WAV via ffmpeg. The light Docker image installs
ffmpeg already. For non-Docker dev install it via your package manager:

```bash
sudo apt install ffmpeg            # Debian / Ubuntu
brew install ffmpeg                # macOS
```

Without ffmpeg, non-WAV uploads still succeed but are flagged
`needs_conversion=true` and downstream stages refuse them. See
[`media-intake-and-providers.md`](media-intake-and-providers.md).

### Phase 4E note: CORS allow-list

If the browser shows "Failed to fetch" even with the correct Backend API Base
URL, the cause is almost always CORS. Phase 4E ships a default allow-list
covering `http://localhost:3000`, `http://localhost:3001`, and the
`127.0.0.1` aliases. Older `.env` files from Phase 4C-D may still have the
single-origin default — regenerate with `cp .env.example .env` and restart
the backend (or `make docker-light-down && make docker-light-up`).

### Docker light runtime (Phase 4C)

For the metadata-only stack in Docker (backend + frontend + orchestrator-idle
+ postgres + redis, with no GPU and no model containers):

```bash
cp .env.example .env             # first time only
make docker-config-check         # validates compose.dev/prod/gpu configs
make docker-light-build          # builds aivideo-backend / orchestrator / frontend
make docker-light-up             # starts postgres + redis + backend + frontend + orchestrator
make docker-light-smoke          # curls /healthz, /api/v1/*, frontend /
make docker-light-down           # stops the stack
```

`make docker-light-check` chains all of the above into a single end-to-end
verification. See [`docker-light-runtime.md`](docker-light-runtime.md) for
the full reference, storage-volume layout, and troubleshooting.

## Full-stack prerequisites (needed from Phase 2 onward)

- Ubuntu 22.04+ with Docker Engine ≥ 24 and `docker compose` (v2) installed.
- NVIDIA Container Toolkit configured — see [`gpu-docker.md`](gpu-docker.md).
- At least 1 TB free disk space (model weights are heavy).
- `git`, `make`, `curl`, `jq`, `sha256sum`, `ffmpeg` (host-side, for the download scripts and ad-hoc checks).

## First-time setup

1. Clone the repo and `cd` into it.
2. Copy `.env.example` to `.env` and edit values (especially `JWT_SECRET`, `POSTGRES_PASSWORD`, `MINIO_ROOT_PASSWORD`, `GRAFANA_ADMIN_PASSWORD`).
3. Read `docs/PROJECT_PLAN.md` and `docs/compliance/policy.md` end-to-end.
4. Download model weights:
   - `./scripts/models/download_llm.sh --accept-license`
   - `./scripts/models/download_tts.sh --accept-license`
   - `./scripts/models/download_sdxl.sh --accept-license`
   - `./scripts/models/download_sadtalker.sh --accept-license`
   - `./scripts/models/download_whisper.sh --accept-license`
   - (Identity guard) build the public-figures embedding index per `models/identity_guard/README.md`.
5. Verify weights with `make models-check`.

## Bring up the stack

CPU-only (limited functionality, useful for backend/frontend dev):

```bash
make up
```

With GPU overlay (full pipeline):

```bash
make up-gpu
```

Useful endpoints:

- Frontend: <http://localhost:3000>
- Backend API: <http://localhost:8000/docs>
- MinIO console: <http://localhost:9001>
- Grafana: <http://localhost:3001>

## Common dev tasks

| Task | Command |
|---|---|
| Tail logs | `make logs` |
| List services | `make ps` |
| Run unit tests | `make test-unit` |
| Run integration tests | `make test-integration` |
| Run a real e2e reel (GPU + models required) | `make test-e2e` |
| Lint / format | `make lint` / `make fmt` |
| Security scans | `make scan` |
| Tear down | `make down` |

## Submitting a job (smoke test)

When the backend is up:

```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
        "brief": {
          "topic": "Three tips for sleeping better",
          "tone": "friendly",
          "duration_sec": 30,
          "language": "en"
        },
        "persona": "caucasian_male_30s_neutral",
        "synthetic_person": true
      }'
```

The response includes a `job_id`. Poll `GET /jobs/{job_id}` or open the frontend dashboard to follow progress.

## Resetting local state

> **Caution:** the commands below delete local job data. They do not touch model weights.

```bash
make down
docker volume rm aivideo_postgres aivideo_minio aivideo_redis
```
