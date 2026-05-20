# 01 — Project structure

Audit date: 2026-05-20 · Branch: `main` · Last commit: `8a54cf1 Phase 12 characters providers secrets and model runtimes`
Working tree: **86 uncommitted changed files** (`git status --porcelain | wc -l = 86`).

## Top-level (evidence: `ls -la`)
```
agents/      backend/    common/    configs/   docker/    docs/
frontend/    models/     pipelines/ scripts/   storage/   tests/
workflows/   Makefile    pytest.ini README.md  .env (gitignored)
Raport/      (stray empty dir)        e (transient, not present at re-check)
Raport claude/  (this audit)
```

## Backend (`backend/app`)
- `api/` — routers: characters, jobs, script, providers, audio_fit, qc, export, secrets, uploads, healthz, video, system, artifacts, tts (14 router modules; evidence: `grep APIRouter( backend/app/api/*.py`).
- `models/` — SQLAlchemy models (character, job, artifact, compliance, stage_run, …).
- `schemas/` — Pydantic v2 schemas (`extra="forbid"` used widely).
- `services/` — business logic incl. `image_providers/` package, `character_image_service.py`, `character_prompt_builder.py`, `image_workflow_select.py`, `image_audit.py`, `image_face_score.py`, `provider_registry.py`.
- `core/` — config, db, deps.

## Alembic migrations (10) — `backend/alembic/versions/`
```
0001_initial · 0002_recovery · 0003_language_subtitles · 0004_characters ·
0005_api_secrets · 0006_face_locked · 0007_job_type_scene_plan ·
0008_orientation · 0009_full_body_reference · 0010_phase_ig3_image_role_metadata
```
Live DB head = **`0010_ig3_image_meta`** (note: the 0010 file's revision id was shortened from a 34-char id to fit the `alembic_version varchar(32)` column; the host file is correct, the DB is at 0010).

## Frontend (`frontend/app` — Next.js App Router)
Pages: `/` (redirect→/characters), `/characters`, `/characters/new`, `/characters/[id]`, `/jobs`, `/jobs/new`, `/jobs/[jobId]`, `/jobs/[jobId]/edit`, `/uploads`, `/settings`, `/technical-help`. 38 components.

## Workflows
`workflows/comfyui/` — 4 templates (`sdxl_initial`, `sdxl_instantid_consistent`, `pulid_flux_initial`, `pulid_flux_consistent`) + README.

## Models on disk (`models/` = 317 GB)
Present: `image/sdxl/sdxl-base-1.0/sd_xl_base_1.0.safetensors` (6.9 GB), sdxl-turbo, ssd-1b, `image/flux/flux.1-schnell`, `image/sd35`. **Absent:** any instantid / pulid / controlnet / insightface / ip-adapter weights (evidence: `find models/ -iname '*instantid*' …` → empty).
