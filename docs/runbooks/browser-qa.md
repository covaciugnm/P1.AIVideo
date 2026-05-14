# Browser QA checklist (Phase 4G)

Quick manual / semi-automatic verification matrix for the metadata-only
operator UI. Run after every UI-touching merge until automated browser
tests land. Curl probes here are scriptable; the page-by-page checks
require a real browser.

## 0. Pre-flight

```bash
test -f .env || cp .env.example .env

BACKEND_PORT=8001 FRONTEND_PORT=3001 POSTGRES_PORT=5433 REDIS_PORT=6380 \
  NEXT_PUBLIC_API_BASE_URL=http://localhost:8001 \
  docker compose -f docker/compose.dev.yml build backend frontend

BACKEND_PORT=8001 FRONTEND_PORT=3001 POSTGRES_PORT=5433 REDIS_PORT=6380 \
  NEXT_PUBLIC_API_BASE_URL=http://localhost:8001 \
  docker compose -f docker/compose.dev.yml up -d \
    postgres redis backend frontend orchestrator
```

If `GET /api/v1/jobs` returns 500 with
`column jobs.<something> does not exist`, your Postgres volume predates
a schema-changing phase (no Alembic migrations yet — dev only). Recover
with:

```bash
make docker-light-reset      # drops postgres/redis/inputs/artifacts volumes
# then re-run the docker compose up command above
```

## 1. Scriptable smoke (curl)

```bash
curl -fsS http://localhost:8001/healthz
curl -fsS http://localhost:8001/api/v1/system/status
curl -fsS http://localhost:8001/api/v1/jobs
curl -fsS http://localhost:8001/api/v1/jobs?status=pending_compliance
curl -fsS http://localhost:8001/api/v1/jobs?status=not_a_status -o /dev/null -w "%{http_code}\n"  # expect 422
curl -fsS http://localhost:8001/api/v1/providers
curl -fsS http://localhost:8001/api/v1/config/ui-options
curl -fsS -o /dev/null -w "HTTP %{http_code}\n" http://localhost:3001/
```

Expected: every probe returns 200 except the deliberate 422.

## 2. Routes (open in browser)

| Route | Must work |
|---|---|
| `/` | Dashboard loads. List shows status + progress + QC + Final-export columns. |
| `/jobs` | Status filter dropdown. View / Edit / Delete actions. |
| `/jobs/new` | Brief + duration + voice + face + compliance form. Provider dropdowns. Upload controls. Generate audio button. |
| `/jobs/[jobId]` | Uses `/summary` (verify in right-sidebar Logs: "detail loader using /summary"). Stage-counts strip below progress. |
| `/jobs/[jobId]/edit` | Pre-compliance fields editable; post-compliance fields locked with banner. |
| `/uploads` | Three upload cards. Recent uploads list. Copy-to-clipboard buttons. |
| `/settings` | Wide settings panel with providers + Docker ports + compose-up command preview. |

## 3. Right sidebar

- **Logs tab**: live entries from frontend + api + backend. Source filter respected. Clear button empties buffer.
- **Settings tab**: backend URL editable, port table editable, "Test backend connection" works (returns app_name+phase on success), Reset to defaults works.
- **Backend status badge** (header): green dot when reachable, red on outage, shows active URL.
- **Collapse rail**: persists across reloads.

## 4. Uploads

| Upload | Steps |
|---|---|
| Text | `/uploads` → Text card → fill script_text → Register text. Confirm artifact_id appears in "Recent uploads". |
| WAV audio | Browse a `.wav` → Upload. `audio_ref` returned. Click play in the audio preview to listen. |
| MP3 audio | Browse a `.mp3` → Upload. With ffmpeg in container, conversion succeeds and `audio/wav` is registered. |
| Image | Browse a `.png` / `.jpg` / `.webp` → Upload. Inline preview renders. |

## 5. Create-job flows

### TTS flow

1. `/jobs/new` → brief → duration → voice mode = TTS → fill script_text.
2. Click **Generate audio** — expect `503 tts_provider_not_configured` shown inline as "Provider 'piper' is not configured…". Logs panel records `tts-generate tts_provider_not_configured`.
3. Tick the four compliance boxes → submit.
4. Redirected to `/jobs/{id}`. Job appears in `pending_compliance`.

### Provided-audio flow

1. `/jobs/new` → switch voice mode to "Use provided audio".
2. Upload a WAV (or MP3 — server converts).
3. Tick `audio_consent` + `audio_owned`.
4. (Optional) tick "Attach a portrait/face image", upload PNG/JPG/WebP, tick the two image consent flags.
5. Submit. Job appears.

## 6. Jobs management

- **View** → opens `/jobs/{id}`.
- **Edit** → opens `/jobs/{id}/edit`. Editing `brief` + `target_duration_seconds` saves. Past-compliance jobs lock script + voice/face mode.
- **Delete** → inline confirmation row. Confirming removes the job + cascades stage_runs + artifacts.

## 7. Known limitations

- Real TTS / lip-sync / video generation are NOT enabled. The Generate audio button always returns `tts_provider_not_configured` until Phase 5A wires Piper.
- Logs are per-tab in-memory only.
- Editing Docker ports in the UI is documentation only — it does NOT reconfigure the running stack. Use the **Copy command** button + restart compose.
- No Alembic migrations yet — adding a model column requires wiping the dev Postgres volume via `make docker-light-reset` for older databases.

## 8. Tear down

```bash
docker compose -f docker/compose.dev.yml down
```
