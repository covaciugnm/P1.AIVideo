# Piper TTS runtime (Phase 6C → Phase 8G opt-in install)

Phase 5A wired `/api/v1/tts/generate` to a real Piper synthesis path
gated by runtime + asset checks. **Phase 8G added a clean opt-in
install path** so operators can enable Piper at backend-build time
without forking the Dockerfile or installing into the host venv. This
runbook covers what an operator needs to **enable** that path. Nothing
here installs or downloads anything automatically — Piper is opt-in.

## Phase 8G — opt-in install via Docker build arg

```bash
INSTALL_PIPER=true \
  POSTGRES_PORT=5433 BACKEND_PORT=8001 FRONTEND_PORT=3010 \
  NEXT_PUBLIC_API_BASE_URL=http://localhost:8001 \
  docker compose -f docker/compose.dev.yml build backend
```

What this does:

- Adds one `RUN pip install piper-tts>=1.2` step gated by the build
  arg. Default is `false` so the light backend stays lean.
- Pulls in `piper-tts` + its `onnxruntime` wheel (~50 MB).
- The provider code path (`agents.voice.providers.piper.provider`) is
  unchanged — it has always detected runtime presence via
  `importlib.util.find_spec("piper")` and gates on assets via
  `PIPER_MODELS_ROOT`.

Operators using a non-Docker venv install can do the same via the new
`tts` extra:

```bash
pip install -e ./backend[tts]
```

## Phase 8G fix — VoiceRequest schema

A latent bug in `/api/v1/tts/generate` constructed `VoiceRequest`
without the required `job_id` and passed a `Path` where a `str` was
expected. That path had never been live-exercised because Piper
isn't installed by default. Phase 8G fixed it; the new success-path
test pins the contract by registering a real audio artifact through
the API.

## Boundaries

- No voice cloning. Piper voices are operator-placed `.onnx` files only.
- No model auto-download. `ALLOW_MODEL_AUTODOWNLOAD=false` is the only
  supported value; the flag is reserved for a future explicit fetch
  helper.
- No external TTS API.
- No GPU dependency. Piper runs on CPU.

## Status states surfaced by the backend

`GET /api/v1/providers/tts` returns one row per known TTS provider. The
Piper row's `status` reflects readiness:

| API `status` | Operator-facing meaning | What's missing |
|---|---|---|
| `not_configured` | `runtime_missing` *or* root unset | Install `piper-tts` package **or** set `PIPER_MODELS_ROOT` |
| `configured` | `assets_missing` | Runtime + root present; voice `.onnx` + `.onnx.json` not on disk |
| `available` | `ready` | Everything present; `/api/v1/tts/generate` will synthesise |

The `notes` field on each row distinguishes the two `not_configured`
sub-cases and tells the operator the exact next step.

`POST /api/v1/tts/generate` mirrors the same categorisation as a 503
detail dict with a `code` field:

| 503 `code` | Reason |
|---|---|
| `tts_runtime_missing` | `piper-tts` not importable |
| `tts_assets_missing` | Voice files not under `PIPER_MODELS_ROOT` |
| `tts_provider_not_configured` | Root env var unset |
| `tts_provider_not_implemented` | Operator picked a provider id ≠ `piper` |
| `tts_generation_failed` | Runtime crashed (defensive) |

## 1. Install Piper

```bash
# In the same venv the backend runs from.
pip install piper-tts
```

(Or rebuild the backend image with `piper-tts` baked in — see "Docker
support" below.)

Verify:

```bash
python -c "import piper; print('ok')"
```

If you skip this step, `GET /api/v1/providers/tts` reports
`status=not_configured` and `notes` starts with "piper-tts runtime not
installed".

## 2. Place a voice manually

Pick a voice from the official Piper voices index (link below). You
need **two** files per voice — the model and its config:

- `<voice-id>.onnx`
- `<voice-id>.onnx.json`

Place both under your chosen `PIPER_MODELS_ROOT`, e.g.:

```
/models/tts/piper/
├── en_US-amy-medium.onnx
└── en_US-amy-medium.onnx.json
```

> **Why manual?** Piper voices vary in license. Auto-downloading would
> bypass the operator's per-voice license check. The project keeps
> `ALLOW_MODEL_AUTODOWNLOAD=false` and never reaches out at runtime.
> Reference index: <https://github.com/rhasspy/piper/blob/master/VOICES.md>

## 3. Configure env vars

Add the relevant lines to `.env` (or rely on the defaults from
`.env.example`):

```bash
# Provider selection.
TTS_BACKEND=piper                       # canonical
# (TTS_PROVIDER=piper would be equivalent; the runtime reads
#  TTS_BACKEND today and providers.py treats them interchangeably
#  through the registry.)

# Where the voice files live.
PIPER_MODELS_ROOT=/models/tts/piper     # or any host path you mount
TTS_MODELS_ROOT=/models/tts             # fallback root used when
                                        # PIPER_MODELS_ROOT is empty

# Which voice to use by default.
TTS_DEFAULT_VOICE=en_US-amy-medium      # ≈ PIPER_VOICE_ID in the spec

# Safety.
ALLOW_MODEL_AUTODOWNLOAD=false          # must stay false
```

The path-derived properties `PIPER_VOICE_MODEL_PATH` /
`PIPER_VOICE_CONFIG_PATH` are computed inside the provider as
`{PIPER_MODELS_ROOT}/{TTS_DEFAULT_VOICE}.onnx` and `… .onnx.json`. If
you need an unusual layout, symlink the files into the expected names —
the provider deliberately does NOT walk subdirectories.

## 4. Check provider status

```bash
curl -fsS http://localhost:8000/api/v1/providers/tts | python -m json.tool
```

Expect the Piper row's `status` to walk through this ladder as you
complete the steps above:

```
not_configured  (piper-tts not installed)
not_configured  (root unset)
configured      (voice files not found under root)
available       (everything ready)
```

## 5. Generate a WAV from /api/v1/tts/generate

Once Piper reports `available`:

```bash
curl -fsS -X POST http://localhost:8000/api/v1/tts/generate \
  -H "Content-Type: application/json" \
  -d '{"script_text":"Hello, this is a Piper test.","tts_provider_id":"piper"}'
```

Expected: HTTP 201 with a JSON body carrying `artifact_id`, `uri`,
`mime_type=audio/wav`, `duration_seconds`, `sample_rate`, `channels`.
The generated WAV is registered as `ArtifactType.audio` and accessible
via `GET /api/v1/artifacts/{artifact_id}/content`.

## 6. Listen in the UI

1. Open the right sidebar → Settings.
2. Confirm **Providers → TTS** shows Piper as `available`.
3. On `/jobs/new`:
   - Voice mode = TTS.
   - Fill brief + script_text.
   - Click **Generate audio**.
4. The audio appears below the script with a playable HTML5
   `<audio>` control — backed by
   `GET /api/v1/artifacts/{id}/content`.

## 7. Debugging missing runtime / missing assets

| Symptom | Likely fix |
|---|---|
| Generate audio surfaces "Provider 'piper' is not configured" | Install `piper-tts` in the backend venv / image |
| Notes say "Set PIPER_MODELS_ROOT" | Add `PIPER_MODELS_ROOT=...` to `.env` and restart |
| Notes say "voice files not found" / "Place .onnx + .onnx.json" | Drop the two files into `PIPER_MODELS_ROOT` (filenames must match `TTS_DEFAULT_VOICE`) |
| 503 with code `tts_generation_failed` | Check backend logs — Piper threw inside `synthesize()`. The endpoint scrubs the partial WAV before responding. |
| Status is `available` but UI button still 503s | Confirm `tts_provider_id=piper` in the request body; other ids return `tts_provider_not_implemented`. |
| Audio plays but is empty / silent | The provider only produces what the model knows — try a longer script or a different voice. |

## Docker support

The Phase 4C light backend image deliberately does **not** bundle
Piper. Two reasons:

1. The `piper-tts` wheel + native deps add ~80 MB and pull in ONNX
   runtime; the light image stays under 350 MB without them.
2. The voice files themselves aren't shipped — installing Piper without
   voices yields a `configured`-not-`available` state that's confusing
   in a fresh smoke run.

When you do want Piper inside the backend image, the documented path is:

```dockerfile
# In a downstream Dockerfile that extends the light image.
FROM aivideo-backend:latest

USER root
RUN pip install --no-cache-dir piper-tts
USER app

# Expect the operator to bind-mount voice files at runtime:
#   docker run -v $(pwd)/models/tts/piper:/models/tts/piper:ro …
```

GPU integration (`Dockerfile.cuda`) stays untouched — Piper is CPU
only.

## Optional real-runtime tests

Tests under `tests/integration/test_phase5a_tts_runtime.py` exercise
the missing-runtime + missing-assets paths against an in-memory app.
Real synthesis tests would need:

- `piper-tts` installed in the venv.
- A voice on disk under a tmp `PIPER_MODELS_ROOT`.
- `RUN_REAL_PIPER_SMOKE=1` env (planned — currently the real-synthesis
  test is left as a documented stub since the project deliberately
  doesn't bundle a voice file).

Until then, the existing skip-on-missing tests are the load-bearing
guarantee that the contract holds.

## Cross-references

- `backend/app/api/tts.py` — categorised 503 contract + real
  generation path.
- `backend/app/api/providers.py::_tts_providers()` — readiness status
  logic.
- `agents/voice/providers/piper/provider.py` — Phase 3B PiperProvider
  + asset checks.
- `tests/integration/test_phase5a_tts_runtime.py` — assertions per
  state.
- `docs/runbooks/media-intake-and-providers.md` — operator-side audio
  ingest + provider catalog overview.
