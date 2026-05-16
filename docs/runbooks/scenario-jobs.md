# Scenario Jobs — Phase 8E Operator Smoke

Eight scenario jobs that cover every realistic path through the
current product, without faking GPU or paid-API behavior. Use them to
test the operator UI end-to-end whenever you spin up the Docker stack.

> **Idempotent**: every brief is timestamped + prefixed `Scenario N — `,
> so re-running the seeder appends jobs rather than mutating existing
> ones. The script never deletes jobs / artifacts / volumes.

## How to run

```bash
# Default: against http://localhost:8001 (Phase 8E alt-port stack)
make scenario-jobs

# Custom backend URL
BACKEND_BASE_URL=http://localhost:8000 make scenario-jobs

# Verify the seeded jobs are visible
make scenario-jobs-check
```

The script:

- POSTs each scenario to `/api/v1/jobs/from-inputs` via stdlib only
  (no `requests` / `httpx` dependency added).
- Generates tiny fixtures **in-memory**: a 300 ms silent WAV (stdlib
  `wave`), a 64×64 white PNG (hand-rolled CRC + zlib), and — if
  `ffmpeg` is on the host PATH — a 300 ms silent MP3 for the
  conversion-path scenario.
- Prints a structured JSON summary to stdout + one `[PASS/FAIL]` line
  per scenario to stderr.

## Scenario matrix

| # | Label | Provider selection | Voice | Face | Expected runtime behavior |
|---|---|---|---|---|---|
| 1 | Template + Piper TTS | `script=template`, `tts=piper` | tts (inline script) | none | Job created. TTS preview returns `tts_runtime_missing` or `tts_assets_missing` unless Piper is installed + voices placed. |
| 2 | Mock + Piper TTS | `script=mock`, `tts=piper` | tts | none | Same as #1; mock LLM is built-in so script preview always works. |
| 3 | Provided WAV + `ffmpeg_convert` | `audio_processor=ffmpeg_convert` | provided_audio | none | Uploads a 300 ms WAV via `/api/v1/uploads/audio`; job links to the artifact. |
| 4 | Provided MP3 → WAV | (defaults) | provided_audio | none | Generates an MP3 via host ffmpeg; backend's Phase 4F path transcodes to WAV (`metadata_summary.converted_to_wav=true`). Auto-skips if host has no ffmpeg. |
| 5 | Image + `stdlib_image_validation` | `image_processor=stdlib_image_validation` | tts | provided_image | Uploads a 64×64 PNG; job inspects via the stdlib image validator. |
| 6 | Audio+image+SadTalker | `video=sadtalker`, `audio_processor=ffmpeg_convert`, `image_processor=stdlib_image_validation` | provided_audio | provided_image | Job stored. `/api/v1/video/generate` returns clean `provider_not_implemented` (real-inference gate off) or `video_assets_missing`/`video_gpu_missing` once Phase 7D flags are flipped — no fake MP4. |
| 7 | Full provider matrix | All five categories | tts | none | Provider selection round-trips on `GET /api/v1/jobs/{id}` and `GET /api/v1/jobs/{id}/summary`. |
| 8 | Future unknown provider ids | `script=custom_future_llm`, `tts=custom_future_tts`, `video=custom_future_video` | tts | none | Phase 6D contract: unknown ids accepted at write time; runtime is the gate. UI must not crash on rendering unknown ids. |

## What each scenario proves

- **#1–#2** — the upload-intake path accepts `provider_selection` (the
  Phase 8E `extra_forbidden` regression that triggered this phase).
  Both `template` and `mock` LLM previews are available even in the
  light backend.
- **#3** — audio uploads land under `UPLOAD_AUDIO_ROOT`, become an
  `ArtifactType.audio` row, and `/api/v1/audio/fit-check` runs against
  them.
- **#4** — Phase 4F ffmpeg transcode is exercised end-to-end. Skip is
  honest when ffmpeg is absent.
- **#5** — Phase 3E image validator + Phase 6D
  `stdlib_image_validation` audit row.
- **#6** — Phase 7B / 7D SadTalker readiness surface is reachable via
  the API but never fakes a video.
- **#7** — every Phase 6D category persists.
- **#8** — Phase 6D "accept future ids" contract.

## Inspecting in the UI

After `make scenario-jobs`:

1. Open <http://localhost:3001> (alt-port stack — adjust if you remap).
2. Job list view shows all eight (or 16, if you ran the seeder twice).
   The status filter still works.
3. Click any job → Job Detail. Confirm:
   - `provider_selection` is populated under the metadata block.
   - For #3 / #4 / #5 / #6 the uploaded artifacts appear in the
     Artifacts table.
   - The Video Preview card appears only when a job has a real video
     or final_export artifact (no fake previews).
4. For #6, the QC and final-export cards stay in metadata-only mode
   until you opt in to real SadTalker (`SADTALKER_ENABLE_REAL_INFERENCE=true`
   + `RUN_REAL_SADTALKER=1` + GPU + weights).

## Data safety

- The seeder uses only `POST` endpoints. **No** delete, no
  `DROP/TRUNCATE`, no volume operations.
- Re-running the seeder always appends. The Phase 8E persistence
  test (`make docker-light-stop` + `make docker-light-start`) keeps
  every scenario job intact.
- Tiny fixtures live only inside the running process / DB rows. No
  binary blobs are added to the repo.
