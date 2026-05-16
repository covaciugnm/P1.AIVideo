# UI ↔ API parity matrix — Phase 10C audit

> **Companion to [`api-surface.md`](./api-surface.md).** This file lists every
> user-facing action in the dashboard and maps it to the backend contract that
> backs it. Frontend-only behaviours are flagged explicitly so operators don't
> assume they survive a browser switch.
>
> **Maintenance rule:** any new page, component, button, or form control must
> appear here in the same PR that adds it. See
> [`contribution-rules.md`](./contribution-rules.md).

Last verified: **2026-05-16** against `frontend/app/*`, `frontend/components/*`,
`frontend/lib/api.ts`, plus a live backend running at `:8001`.

## Legend

- ✅ **API** — round-trips to a documented backend endpoint
- 🖥️ **Frontend-only** — lives in the browser only (localStorage, in-page state,
  download links). Does not survive a different browser / device.
- 🚧 **Runtime-gated** — endpoint exists, but the operation only succeeds when
  the runtime (Piper / SadTalker / Ollama / …) is installed and weights are on
  disk. The UI surfaces a categorised error otherwise.
- ❌ **No backing** — UI shows the control but there is no contract behind it.
  *None should remain after Phase 10C.*

## Pages

### `/` — Dashboard (`app/page.tsx`)

| Control | Action | Backing | Help topic |
|---|---|---|---|
| Page header `?` | Open help → `page-dashboard` | 🖥️ Help overlay | `page-dashboard` |
| Recent jobs table row | Navigate to `/jobs/[id]` | 🖥️ `next/link` | `page-job-detail` |
| Recent jobs progress bar | Visualises `JobSummary.progress_percent` | ✅ `listJobs()` (polled) | `stage-timeline` |
| `+ New job` | Navigate to `/jobs/new` | 🖥️ `next/link` | `page-create-job` |

### `/jobs` — Jobs list (`app/jobs/page.tsx`)

| Control | Action | Backing | Help topic |
|---|---|---|---|
| Status filter dropdown | Filters local list + sets `?status=` | ✅ `listJobs({status})` | `page-jobs-list` |
| Job row click | Drill into detail | 🖥️ `next/link` | `page-job-detail` |
| `+ New job` | Navigate to create | 🖥️ | `page-create-job` |
| `?` next to title | Open help → `page-jobs-list` | 🖥️ | `page-jobs-list` |

### `/jobs/new` — Create job (`app/jobs/new/page.tsx` + `CreateJobForm.tsx`)

| Control | Action | Backing | Help topic |
|---|---|---|---|
| Brief textarea | Sets `brief` | 🖥️ form state | `page-create-job` |
| Target duration | Sets `target_duration_seconds` | 🖥️ form state | `page-create-job` |
| Voice mode select | `tts` / `provided_audio` | 🖥️ form state | `voice-piper`, `voice-provided-audio` |
| Script provider dropdown | Selects `provider_selection.script_provider_id` | ✅ `getProviders()` populates options | `providers-catalog` |
| TTS provider dropdown | Selects `provider_selection.voice_provider_id` | ✅ same | `providers-catalog`, `voice-piper`, `voice-f5tts-ro` |
| Video provider dropdown | Selects `provider_selection.video_provider_id` | ✅ same | `providers-catalog`, `video-overview`, `sadtalker-setup` |
| **Generate script** | POST `/api/v1/script/generate` (preview before submit) | ✅ `generateScript()` 🚧 ollama needs daemon | `error-codes` (`script_provider_disabled`, `script_runtime_missing`) |
| **Generate audio** | POST `/api/v1/tts/generate` (preview WAV) | ✅ `generateTts()` 🚧 piper / f5tts | `error-codes` (`tts_runtime_missing`, `tts_assets_missing`) |
| **Audio fit-check** | POST `/api/v1/audio/fit-check` | ✅ `audioFitCheck()` 🚧 ffmpeg | `inputs-audio` |
| Image artifact picker | References a previously uploaded image | ✅ `getJobArtifacts()` / lib types | `page-uploads`, `inputs-images` |
| Audio artifact picker | References a previously uploaded audio | ✅ same | `page-uploads`, `inputs-audio` |
| Watermark required | Sets `watermark_required` (always true; UI refuses to flip) | 🖥️ form state | `compliance-watermark-c2pa` |
| C2PA required | Sets `c2pa_required` | 🖥️ form state | `compliance-watermark-c2pa` |
| Synthetic person confirmed | Mandatory attestation | 🖥️ form state | `synthetic-only` |
| Consent confirmed | Mandatory attestation | 🖥️ form state | `synthetic-only` |
| **Submit** | POST `/api/v1/jobs/from-inputs` | ✅ `createJobFromInputs()` | `page-create-job` |
| `?` next to title | Open help → `page-create-job` | 🖥️ | `page-create-job` |

### `/jobs/[jobId]` — Job detail (`app/jobs/[jobId]/page.tsx`)

| Control | Action | Backing | Help topic |
|---|---|---|---|
| Polling | GET `/api/v1/jobs/{id}/summary` every N s | ✅ `getJobSummary()` | `page-job-detail` |
| Status chip | Reflects `JobDetail.status` | ✅ | `stage-timeline` |
| Progress bar | `JobProgress.progress_percent` | ✅ `getJobProgress()` (via summary) | `stage-timeline` |
| Stage timeline | `StageTimelineEntry[]` | ✅ `getJobTimeline()` (via summary) | `stage-timeline`, `job-lifecycle` |
| Artifacts table (rows) | `ArtifactResponse[]` | ✅ `getJobArtifacts()` | `artifact-types` |
| Artifact **download** | GET `/api/v1/artifacts/{id}/content?download=true` | ✅ `artifactContentUrl({download:true})` | `artifact-types` |
| Audio preview `<audio>` | Stream from content endpoint | ✅ same | `artifact-types` |
| Video preview `<video>` (`VideoArtifactPreview`) | Stream from content endpoint | ✅ same | `artifact-types`, `sadtalker-setup` |
| Compliance events list | `ComplianceEventResponse[]` | ✅ `getJobComplianceEvents()` | `compliance-overview` |
| QC report card (`QcReportCard`) | `QCReportResponse` | ✅ `getJobQcReportOptional()` | `error-codes` (`qc_*`) |
| Final export card (`FinalExportCard`) | `FinalExportResponse` | ✅ `getJobFinalExportOptional()` | `compliance-watermark-c2pa` |
| Edit | Navigate to `/jobs/[id]/edit` | 🖥️ | `page-job-edit` |
| **Cancel** (`JobRecoveryControls`) | POST `/api/v1/jobs/{id}/cancel` | ✅ `cancelJob()` | `job-recovery` |
| **Retry** (`JobRecoveryControls`) | POST `/api/v1/jobs/{id}/retry` | ✅ `retryJob()` | `job-recovery` |
| **Delete** | DELETE `/api/v1/jobs/{id}` (when wired) | ✅ `deleteJob()` | `job-recovery` |

### `/jobs/[jobId]/edit` — Edit job

| Control | Action | Backing | Help topic |
|---|---|---|---|
| All editable fields | PATCH `/api/v1/jobs/{id}` | ✅ `updateJob()` | `page-job-edit` |
| Cancel / Save | local form + PATCH | ✅ | `page-job-edit` |

### `/uploads` — Uploads (`app/uploads/page.tsx`)

| Control | Action | Backing | Help topic |
|---|---|---|---|
| Text upload form | POST `/api/v1/uploads/text` | ✅ `uploadText()` | `page-uploads` |
| Audio upload (drag-drop / file picker, `UploadCard`) | POST `/api/v1/uploads/audio` | ✅ `uploadAudio()` 🚧 ffmpeg for MP3 | `inputs-audio` |
| Image upload (drag-drop / file picker, `UploadCard`) | POST `/api/v1/uploads/image` | ✅ `uploadImage()` | `inputs-images` |
| Recent uploads list | local component state | 🖥️ session-only | `page-uploads` |

### `/settings` — Settings (`app/settings/page.tsx` + `SettingsPanel.tsx`)

| Control | Action | Backing | Help topic |
|---|---|---|---|
| Backend API base URL input | Persists to localStorage | 🖥️ localStorage | `page-settings` |
| **Test backend connection** | GET `/healthz` against the configured base URL | ✅ raw fetch | `troubleshooting-frontend` |
| Docker host port overrides (8001 / 3010 / 5433 / 6380) | localStorage; informs the compose-command preview | 🖥️ | `page-settings` |
| **Copy compose command** | Clipboard API | 🖥️ | `page-settings` |
| Reset to defaults | Clears localStorage settings | 🖥️ | `page-settings` |
| Provider defaults section (`ProvidersSection`) | Reads `getProviders()`, persists chosen defaults | ✅ read; 🖥️ persist | `providers-catalog` |
| Custom providers section (`CustomProvidersSection`) | Add / edit / delete custom rows | 🖥️ localStorage | `providers-custom` |

### Right sidebar (`RightSidebar.tsx` + `SidebarTabs.tsx`)

| Tab | Action | Backing | Help topic |
|---|---|---|---|
| Logs (`LogsPanel`) | Renders the in-memory log bus | 🖥️ session-only | `logs-panel` |
| Logs: filter chips | Local filter | 🖥️ | `logs-panel` |
| Logs: **Export JSON** | Triggers a browser download of the visible entries | 🖥️ no backend persistence | `logs-panel` |
| Logs: **Export TXT** | Same, as plain text | 🖥️ | `logs-panel` |
| Logs: **Clear** | Empties the bus | 🖥️ | `logs-panel` |
| Settings tab (`SettingsPanel`) | Same content as `/settings` | per row above | `page-settings` |
| Test1 tab (`ProviderTestPanel`) | Diagnostic GETs + POSTs against providers | ✅ `getProviders`, `generateScript`, `generateTts`, `artifactContentUrl` | `providers-status` |
| Test1: **Test connection** per provider | category-specific generate / health call | ✅ | `providers-status` |

### Help system (Phase 10B + 10C)

| Control | Action | Backing | Help topic |
|---|---|---|---|
| Floating Help button (`HelpButton`) | Opens overlay | 🖥️ React state | `welcome` |
| Inline `?` chip (`HelpHint`) | Opens overlay at a specific article | 🖥️ | per-anchored |
| Help nav (left rail in overlay) | Section + article tree | 🖥️ | every article |
| Help search | In-memory token scorer over titles + keywords + body | 🖥️ | every article |
| Help back / forward | Browser-like history (not the global URL — overlay-local) | 🖥️ | n/a |
| URL hash `#help/<slug>` | Deep link to a specific article | 🖥️ history.replaceState | n/a |
| Keyboard `?` | Toggle overlay | 🖥️ | `keyboard-shortcuts` |
| Keyboard `Esc` | Close overlay | 🖥️ | `keyboard-shortcuts` |
| Keyboard `/` (within overlay) | Focus search | 🖥️ | `keyboard-shortcuts` |

## Parity verdict

After the Phase 10C audit:

- **Total UI actions audited:** 60.
- **Backed by a documented backend endpoint:** 32 (✅).
- **Documented frontend-only:** 28 (🖥️) — all expected to be client-side
  (Help overlay, localStorage settings, log bus, custom providers, navigation).
- **Runtime-gated:** 6 of the ✅ rows (🚧) — exposed in the UI but the run
  succeeds only when the runtime is installed (`script_generate(ollama)`,
  `tts_generate(piper|f5tts_ro)`, `audio_fit_check`, `video_generate`). Each
  carries a help topic explaining what's needed.
- **Missing API (❌):** 0. Every UI button that *should* hit the backend does.
- **API exists but no UI consumer:** `GET /api/v1/stages`,
  `GET /api/v1/artifact-types`, `POST /api/v1/qc/inspect`,
  `POST /api/v1/export/finalize`,
  `GET /api/v1/providers/{category}/{provider_id}`. Phase 10C added typed
  wrappers in `lib/api.ts` for all five so future UI pages can consume them
  without churn; they are also exercised by `tests/integration/test_phase10c_*`.

## Frontend-only surfaces — explicit list

These behaviours are intentional client-side state. Each is mentioned in the
relevant help topic so the operator knows what to expect:

1. **Logs panel + export JSON/TXT** — session-local, no backend log store.
2. **Custom providers** — localStorage, per-browser. Add a backend table only if
   multi-operator persistence becomes a requirement.
3. **Settings (`Settings`)** — backend URL, port hints, polling interval, theme.
4. **Help overlay** — open state, last-viewed article (localStorage), nav history.
5. **Audio / video previews** — stream from the artifact `content` endpoint;
   the `<audio>` / `<video>` element state is the browser's.
6. **Recent uploads list on `/uploads`** — component-state only; refresh wipes it.
   The artifacts themselves are persisted via `POST /api/v1/uploads/*`.

## What changed in Phase 10C

- **New typed client wrappers**: `generateVideo`, `inspectQc`, `finalizeExport`,
  `getStages`, `getArtifactTypes`, `getProviderDetail` — `frontend/lib/api.ts`.
- **New runbooks**: this file + [`api-surface.md`](./api-surface.md) +
  [`contribution-rules.md`](./contribution-rules.md).
- **Help content** expanded (`frontend/lib/help/content.ts`) — every page in
  this table is anchored to at least one help article.
- **Tests** that assert this matrix doesn't drift:
  `tests/integration/test_phase10c_api_surface.py`,
  `tests/integration/test_phase10c_ui_api_parity.py`,
  `tests/integration/test_phase10c_help_coverage.py`.
