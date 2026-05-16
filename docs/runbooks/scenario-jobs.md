# Scenario Jobs — Phase 8E + Phase 10A-0 Operator Smoke

Two complementary seeders live in `scripts/create_scenario_jobs.py`:

- **Phase 8E** (default mode) — eight timestamped `Scenario N — …` jobs
  that exercise every realistic provider-selection path. Re-running
  appends new timestamped jobs.
- **Phase 10A-0** (`--demo` flag) — eight **idempotent** `Demo — …`
  jobs. Re-running the seeder does not create duplicates: it queries
  `/api/v1/jobs` first and only creates the missing entries. This is
  the persistent demo matrix used to inspect Phase 9 real-vs-metadata
  honesty in the UI.

Both modes share the same safety contract: never deletes anything,
never runs paid APIs, never auto-pulls model weights.

> **Idempotent (Phase 10A-0 mode)**: every `Demo — …` brief is fixed
> and unique. Re-runs query existing jobs and append nothing. The
> script never deletes jobs / artifacts / volumes.

## Phase 10A-0 — `Demo —` matrix (idempotent)

Run via:

```bash
BACKEND_BASE_URL=http://localhost:8001 \
  python3 scripts/create_scenario_jobs.py --demo
```

The 8 scenarios:

| # | Brief | Provider selection | Inputs | Expected runtime outcome (default light backend) |
|---|---|---|---|---|
| 1 | `Demo — Template Script + TTS Piper path` | script=template, tts=piper, video=sadtalker | `script_text` inline | TTS stage: clean `tts_runtime_missing` (Piper not installed); no fake audio |
| 2 | `Demo — Mock Script + TTS Piper path` | script=mock, tts=piper, video=sadtalker | `script_text` inline | same as #1, but mock scriptwriter |
| 3 | `Demo — Ollama Script path` | script=ollama, model=qwen3.6, tts=piper | `script_text` inline | Script stage: `script_provider_unreachable` / `script_model_missing` if daemon/network/model unavailable |
| 4 | `Demo — Provided WAV audio + Provided image + SadTalker selected` | full matrix, sadtalker | tiny WAV + tiny PNG uploaded | Face/voice real artifacts; lipsync stage: clean `video_runtime_missing` (no torch); no fake MP4 |
| 5 | `Demo — MP3 upload conversion path` | full matrix | tiny MP3 uploaded → auto-converted to WAV | Audio artifact records `converted_to_wav=true` if ffmpeg present |
| 6 | `Demo — Future custom providers metadata path` | all `custom_future_*` IDs | `script_text` inline | All stages: clean `not_configured` / `unknown_provider` — UI does not crash |
| 7 | `Demo — Full local best-effort path` | full deterministic matrix (template/piper/sadtalker) | `script_text` inline | Best available result without GPU; placeholder media for stages without real runtime |
| 8 | `Demo — Real video success` | sadtalker + provided WAV + provided PNG | tiny WAV + tiny PNG | **Only created when** SadTalker readiness is green (`RUN_REAL_SADTALKER=1`, `SADTALKER_ENABLE_REAL_INFERENCE=true`, weights on disk, GPU visible). Otherwise the seeder records `skipped` with the exact missing gates |

The deliberate honesty: scenarios 1–7 land cleanly without GPU / paid
APIs. Scenario 8 refuses to fake success. **No fake MP4 / fake
portrait / fake narration is ever produced** — Phase 9B/9D enforced
this at the handler level.

### Inspecting Demo jobs

Each created Demo job is reachable at:

```
http://localhost:3001/jobs/<job_id>
```

The job-detail page renders:

- the **provider_selection** badge row;
- the **artifact table** with the Phase 9F "Real file" column (`yes` /
  `manifest` / `metadata-only` / `no`);
- the **QC card** with a `real-media` vs `metadata-only` badge;
- the **Final Export card** with a `real-mp4` vs `manifest-only` badge.

Operator validation checklist for each Demo job:

1. Provider selection on the badge row matches the brief.
2. No artifact row claims a `.png` / `.wav` / `.mp4` URI without a
   real on-disk file backing it.
3. The QC card and Final Export card both surface the metadata-only
   state honestly (no green "real video" claim when no MP4 exists).

### Phase 10A-1 — Romanian F5TTS-Ro demo job

A dedicated demo job exercises the optional Romanian TTS provider:

| Field | Value |
|---|---|
| Brief | `Demo — Romanian F5TTS-Ro voice to video path` |
| Voice mode | `tts` (with Romanian `script_text`) |
| Face mode | `provided_image` (tiny PNG fixture) |
| Provider selection | script=template, **tts=f5tts_ro**, video=sadtalker, audio=ffmpeg_convert, image=stdlib_image_validation |
| Romanian script | "Bună ziua! Acesta este un test de generare video cu voce în limba română. Sistemul folosește un provider TTS românesc și un generator video configurabil." |

Expected outcome on a default light backend (no F5TTS-Ro service
running, no SadTalker GPU):

- `POST /api/v1/tts/generate` with `tts_provider_id=f5tts_ro` →
  503 `tts_provider_not_configured` (until the optional service is
  built + started and `F5TTS_RO_BASE_URL` is set).
- Job created in `pending_compliance`; provider_selection persists; UI
  shows F5TTS-Ro in the TTS dropdown with the `not_implemented` /
  `configured` / `available` status reflecting the env.

To turn the demo into a real audio run:

1. Build + start the optional service: see
   [`docs/runbooks/f5tts-ro-runtime.md`](f5tts-ro-runtime.md).
2. Set `F5TTS_RO_BASE_URL` in the backend env and restart the backend
   container.
3. Re-run the Generate Audio flow from the Job Detail page.

### Phase 10B — Real SadTalker activation attempt (audited 2026-05-16)

Phase 10B attempted to activate scenario 8 ("Real video success") on this
host. **Result: blocked.** Exact missing gates surfaced by
`/api/v1/video/generate` with `SADTALKER_ENABLE_REAL_INFERENCE=true` +
`RUN_REAL_SADTALKER=1`:

```json
{
  "status": "not_configured",
  "error_code": "video_assets_missing",
  "message": "SadTalker weights are not on disk. Missing: ...",
  "output_video_artifact_id": null,
  "metadata": {
    "sadtalker": {
      "details": {
        "assets": {"status": "missing", "missing": [
          "checkpoints/mapping_00109-model.pth.tar",
          "checkpoints/mapping_00229-model.pth.tar",
          "checkpoints/SadTalker_V0.0.2_256.safetensors",
          "checkpoints/SadTalker_V0.0.2_512.safetensors",
          "gfpgan/GFPGANv1.4.pth"
        ]},
        "runtime": {"torch_available": false},
        "gpu": {"available": false, "reason": "torch_missing"}
      }
    }
  }
}
```

So: no GPU on the audit host, no SadTalker weights, no torch in the
light backend. Per Phase 9 honesty contract, **no fake MP4 was
registered**. To unblock, follow `docs/runbooks/sadtalker-runtime.md`
"Phase 10B operator checklist" (5 gates).

### Real-runtime opt-in for Scenario 8

```bash
export SADTALKER_MODELS_ROOT=/path/to/weights
export SADTALKER_ENABLE_REAL_INFERENCE=true
export RUN_REAL_SADTALKER=1
# host must also have a CUDA-capable GPU + torch installed in the
# GPU backend image (see docs/runbooks/sadtalker-runtime.md)
```

Without those, the seeder records:

```json
{
  "scenario": 8,
  "skipped": "Skipped — SadTalker real runtime not ready (no fake success will be claimed)",
  "missing_gates": {
    "status": "not_implemented",
    "SADTALKER_ENABLE_REAL_INFERENCE": false,
    "RUN_REAL_SADTALKER": false
  }
}
```

---

## Phase 8E — timestamped scenarios (legacy)

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
