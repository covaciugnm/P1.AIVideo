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
