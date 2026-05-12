# P1.AIVideo

Docker-based multi-agent pipeline that produces short vertical reels (15–60s) featuring a **fully synthetic** white Caucasian human performing lip-synced narration from a text brief.

> **Current status: Phase 1 — metadata-only flow.**
> The repo currently ships a FastAPI backend, an orchestrator skeleton, and the intake compliance gate (`policy_gate`). **No model inference, no video generation, no lip-sync, no model weights downloaded.** The flow validates consent + compliance flags + a small banned-keyword scan on the brief, persists the job in Postgres, emits a small reference event to Redis, and updates job status to `accepted` or `rejected`.
> See [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) for the full multi-phase plan.

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

## Phase 1 scope (current)

Implemented:

- `POST /jobs` and `GET /jobs/{id}` (FastAPI).
- Job persisted in Postgres (SQLite for tests).
- `job.created` event published to Redis Streams — **reference only, no media**.
- Orchestrator consumer that runs the intake `policy_gate`.
- Compliance Officer's `policy_gate` checks consent/synthetic-person flags + banned-keyword scan, and writes an audit-grade `compliance_events` row.
- Integration test (`tests/integration/test_phase1_metadata_flow.py`) verifies the full path.

Explicitly **not** in Phase 1:

- No model weights are downloaded.
- No GPU libraries (torch / diffusers / SadTalker / MuseTalk / Wav2Lip) are installed.
- No real video, audio, or lip-sync generation.
- No external paid APIs.
- No LangGraph yet — Phase 2 will lift the single-node state machine into a full DAG.

## License

TBD — to be selected at v1 release. Until then, all rights reserved by the project owner.
