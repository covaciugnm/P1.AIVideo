# Backend API surface — Phase 10C inventory

> **Source of truth for the HTTP contract.** Generated and verified against
> `GET /openapi.json` and `backend/app/api/*.py` on **2026-05-16**.
>
> **Rule of thumb:** if you touch a router, schema, or response shape, update this
> file in the same change. See [`contribution-rules.md`](./contribution-rules.md).

Total paths: **45** (35 canonical under `/api/v1/*`, 1 root `/healthz`,
9 legacy `/jobs/*` aliases kept for backwards compatibility).

Legend in the *UI consumer* column:
- ✅ — wired through `frontend/lib/api.ts` typed client
- 🧪 — exercised only by tests / out-of-band tooling
- ✋ — backend-only, no UI consumer today
- ➕ — newly added in Phase 10C

## 1. Health & system

| Method | Path | Request | Response | UI consumer | Runtime needs |
|---|---|---|---|---|---|
| `GET` | `/healthz` | — | `{status, phase, scope}` | ✅ `BackendStatusBadge` (polled) | None |
| `GET` | `/api/v1/system/status` | — | `{app_name, app_version, phase, scope, server_time, database_reachable, database_error}` | ✅ `getSystemStatus()` | DB |
| `GET` | `/api/v1/config/ui-options` | — | `UIOptions` (voice modes, face modes, allowed mime types, max sizes, default providers, …) | ✅ `getUiOptions()` | None |
| `GET` | `/api/v1/config/languages` | — | `LanguagesConfigResponse` (catalog + defaults + subtitle defaults) | ✅ Phase 11A — `LanguageContext` reads on boot | None |
| `GET` | `/api/v1/stages` | — | `[{name, label, description}]` (DAG metadata) | ➕ `getStages()` | None |
| `GET` | `/api/v1/artifact-types` | — | `[{type, label, mime_hint}]` (incl. `subtitle` since Phase 11A) | ➕ `getArtifactTypes()` | None |
| `GET` | `/api/v1/settings/ui` | — | `{ui_language, default_video_language, updated_at}` | ✅ Phase 11A — operator-wide singleton | DB |
| `PATCH` | `/api/v1/settings/ui` | `{ui_language?, default_video_language?}` | same as GET | ✅ Phase 11A | DB |

## 2. Jobs (canonical + legacy alias)

The canonical prefix is `/api/v1/jobs`. The bare `/jobs/*` paths are the legacy
Phase 4B alias — preserved for backwards compatibility with the demo seeder and
older scripts. The frontend uses `/api/v1/*` exclusively.

| Method | Path | Request | Response | UI consumer | Runtime needs |
|---|---|---|---|---|---|
| `GET` | `/api/v1/jobs` | query: `limit`, `offset`, `status` | `JobSummary[]` | ✅ `listJobs()` | None |
| `POST` | `/api/v1/jobs` | `CreateJobBody` | `JobResponse` (201) | ✅ `createJob()` | None |
| `POST` | `/api/v1/jobs/from-inputs` | `CreateJobFromInputsBody` (artifact_ids + brief) | `JobResponse` (201) | ✅ `createJobFromInputs()` | None |
| `GET` | `/api/v1/jobs/{id}` | — | `JobDetail` | ✅ `getJob()` | None |
| `PATCH` | `/api/v1/jobs/{id}` | partial fields | `JobResponse` | ✅ `updateJob()` | None |
| `DELETE` | `/api/v1/jobs/{id}` | — | `204` | ✅ `deleteJob()` | None |
| `GET` | `/api/v1/jobs/{id}/summary` | — | `JobFullSummary` (combined detail+timeline+artifacts+QC+export) | ✅ `getJobSummary()` | None |
| `GET` | `/api/v1/jobs/{id}/progress` | — | `JobProgress` | ✅ `getJobProgress()` | None |
| `GET` | `/api/v1/jobs/{id}/timeline` | — | `StageTimelineEntry[]` | ✅ `getJobTimeline()` | None |
| `GET` | `/api/v1/jobs/{id}/artifacts` | — | `ArtifactResponse[]` | ✅ `getJobArtifacts()` | None |
| `GET` | `/api/v1/jobs/{id}/compliance-events` | — | `ComplianceEventResponse[]` | ✅ `getJobComplianceEvents()` | None |
| `GET` | `/api/v1/jobs/{id}/qc-report` | — | `QCReportResponse` or 404 | ✅ `getJobQcReportOptional()` | None |
| `GET` | `/api/v1/jobs/{id}/final-export` | — | `FinalExportResponse` or 404 | ✅ `getJobFinalExportOptional()` | None |
| `POST` | `/api/v1/jobs/{id}/cancel` | `{reason?}` | `JobResponse` | ✅ `cancelJob()` | None |
| `POST` | `/api/v1/jobs/{id}/retry` | `{stage_name?, reason?}` | `JobResponse` | ✅ `retryJob()` | None |

**Legacy alias** (identical contracts, prefix `/`): `/jobs`, `/jobs/{id}`,
`/jobs/{id}/artifacts`, `/jobs/{id}/cancel`, `/jobs/{id}/compliance-events`,
`/jobs/{id}/final-export`, `/jobs/{id}/progress`, `/jobs/{id}/qc-report`,
`/jobs/{id}/retry`, `/jobs/{id}/summary`, `/jobs/{id}/timeline`. **Do not
add new clients against this alias.**

## 3. Uploads (multipart / JSON intake)

| Method | Path | Request | Response | UI consumer | Runtime needs |
|---|---|---|---|---|---|
| `POST` | `/api/v1/uploads/text` | JSON: `{script_text, title?, language?, tone?, target_duration_seconds?}` | `UploadTextResponse` | ✅ `uploadText()` | None |
| `POST` | `/api/v1/uploads/audio` | multipart `file=@…;type=audio/wav` | `UploadAudioResponse` (artifact id + duration + sample rate + channels + checksum) | ✅ `uploadAudio()` | `ffmpeg` (for MP3 → WAV conversion) |
| `POST` | `/api/v1/uploads/image` | multipart `file=@…;type=image/{png,jpeg}` | `UploadImageResponse` (artifact id + width + height + checksum) | ✅ `uploadImage()` | stdlib PIL |

## 4. Artifacts

| Method | Path | Request | Response | UI consumer | Runtime needs |
|---|---|---|---|---|---|
| `GET` | `/api/v1/artifacts/{id}/content` | query: `download=true` for `Content-Disposition: attachment` | binary stream (`image/*`, `audio/wav`, `video/mp4`, `application/json`) | ✅ `artifactContentUrl()` (used by `VideoArtifactPreview`, `AudioPreview`, `ArtifactTable`) | None |

Artifact metadata is surfaced via `GET /api/v1/jobs/{id}/artifacts`. There is no
dedicated `GET /api/v1/artifacts/{id}` (metadata-only) endpoint — by design,
artifacts are addressed in the context of their owning job.

## 5. Providers

`{category}` is one of `llm`, `tts`, `video_generator`, `audio_processor`,
`image_processor`. The path slug uses kebab-case for multi-word categories.

| Method | Path | Request | Response | UI consumer | Runtime needs |
|---|---|---|---|---|---|
| `GET` | `/api/v1/providers` | — | `ProvidersResponse` (every category as a keyed map) | ✅ `getProviders()` | None |
| `GET` | `/api/v1/providers/llm` | — | `ProviderInfo[]` | ✅ `getProvidersForCategory("llm")` | None |
| `GET` | `/api/v1/providers/tts` | — | `ProviderInfo[]` | ✅ `getProvidersForCategory("tts")` | None |
| `GET` | `/api/v1/providers/video-generators` | — | `ProviderInfo[]` | ✅ `getProvidersForCategory("video_generator")` | None |
| `GET` | `/api/v1/providers/audio-processors` | — | `ProviderInfo[]` | ✅ `getProvidersForCategory("audio_processor")` | None |
| `GET` | `/api/v1/providers/image-processors` | — | `ProviderInfo[]` | ✅ `getProvidersForCategory("image_processor")` | None |
| `GET` | `/api/v1/providers/{category}/{provider_id}` | — | single `ProviderInfo` with full readiness detail | ➕ `getProviderDetail()` | depends on provider |

Each `ProviderInfo` carries a live readiness `status` (`ok` / `available` /
`not_implemented` / `not_configured` / `missing_assets` / `runtime_missing` /
`gpu_unavailable`) and a free-text `notes` field describing what is needed.

## 6. Generation (write paths)

These endpoints attempt actual model invocations or short-circuit to a
categorised error code. They never produce fake content.

| Method | Path | Request | Response | UI consumer | Runtime needs |
|---|---|---|---|---|---|
| `POST` | `/api/v1/script/generate` | `ScriptGenerateRequest` | `ScriptGenerateResponse` or `ScriptGenerateError` (503) | ✅ `generateScript()` (used by Test1 panel + CreateJobForm) | `template` always OK; `ollama` needs daemon |
| `POST` | `/api/v1/tts/generate` | `TTSGenerateRequest` | `TTSGenerateResponse` (201) or `TTSGenerateError` (503) | ✅ `generateTts()` (Test1 panel + CreateJobForm preview) | `piper-tts` python + voices on disk; or `F5TTS_RO_BASE_URL` for f5tts_ro |
| `POST` | `/api/v1/video/generate` | `VideoGenerationRequest` | `VideoGenerationResult` (always 200; categorised `status` + `error_code`) | ➕ `generateVideo()` | SadTalker wrapper service (Phase 10B) reachable at `SADTALKER_BASE_URL`; or in-process torch + weights + GPU |

## 7. Media tools / post-processing

| Method | Path | Request | Response | UI consumer | Runtime needs |
|---|---|---|---|---|---|
| `POST` | `/api/v1/audio/fit-check` | `AudioFitCheckRequest` (artifact_id or local_path + target duration) | `AudioFitCheckResponse` (verdict + adjust suggestions) | ✅ `audioFitCheck()` (CreateJobForm + JobDetail) | `ffmpeg` |
| `POST` | `/api/v1/qc/inspect` | `{job_id}` | `QCReportResponse` (re-runs lip-sync + watermark + AI-disclosure check, persists) | ➕ `inspectQc()` | `ffprobe`, optional lip-sync detector |
| `POST` | `/api/v1/export/finalize` | `{job_id, embed_watermark?, c2pa_required?}` | `FinalExportResponse` | ➕ `finalizeExport()` | `ffmpeg`; optional C2PA signer |

## 8. Cross-cutting concerns

- **Errors are structured.** Every endpoint returns either:
  - HTTP 200/201 with the expected schema, OR
  - HTTP 4xx/5xx with `{"detail": <string | array-of-pydantic-errors>}`, OR
  - HTTP 200 with `{status: "<categorised>", error_code: "<code>", message, metadata}` for generation endpoints whose failure is structured (per Phase 7B contract).
  No endpoint returns HTML, plain-text errors, or raw stack traces. The
  frontend uses `humanizeApiDetail()` in `lib/api.ts` to turn Pydantic v2
  validation arrays into a human sentence.
- **CORS** is configured in `backend/app/main.py` via `CORS_ALLOW_ORIGINS`.
  The light dev defaults allow `http://localhost:3000` and `:3010`.
- **Auth** — none. The dashboard is intended for a private operator on
  localhost. Add a reverse-proxy in front of it for any other deployment.
- **Pagination** — only `GET /api/v1/jobs` paginates (`limit`/`offset`).
  Everything else returns its full payload.
- **OpenAPI** — `GET /openapi.json` (always on). Swagger UI under `/docs`
  when `DEBUG=true`.

## 9. Frontend client coverage

`frontend/lib/api.ts` exports a typed wrapper for **every endpoint** consumed by
the UI. The Phase 10C audit added wrappers for the four endpoints previously
called by raw `fetch`:

- `generateVideo()` — POST `/api/v1/video/generate`
- `inspectQc()` — POST `/api/v1/qc/inspect`
- `finalizeExport()` — POST `/api/v1/export/finalize`
- `getStages()` / `getArtifactTypes()` / `getProviderDetail()` — read-only metadata

Endpoints with **no UI consumer**:
- Legacy `/jobs/*` alias (kept; do not add clients).
- `getStages()` / `getArtifactTypes()` are surfaced for Help/diagnostics tooling
  and the Phase 10C tests; pages don't consume them today.

## 10. Runtime / GPU requirements at a glance

| Endpoint | CPU only | Needs `ffmpeg` | Needs `piper-tts` | Needs `F5TTS-Ro` HTTP | Needs GPU + SadTalker |
|---|---|---|---|---|---|
| `/api/v1/script/generate` | ✓ | | | | |
| `/api/v1/tts/generate` (piper) | | | ✓ | | |
| `/api/v1/tts/generate` (f5tts_ro) | | | | ✓ | |
| `/api/v1/uploads/audio` | | ✓ (MP3→WAV) | | | |
| `/api/v1/audio/fit-check` | | ✓ | | | |
| `/api/v1/video/generate` (sadtalker) | | | | | ✓ |
| `/api/v1/qc/inspect` | | ✓ | | | |
| `/api/v1/export/finalize` | | ✓ | | | |
| everything else | ✓ | | | | |
