# F5TTS-Ro Runtime Runbook — Phase 10A-1

This runbook covers the **optional**, **operator-installed** Romanian TTS
provider that fronts upstream [F5-TTS](https://github.com/SWivid/F5-TTS)
configured for Romanian via the
[racai-ro/Ro-F5TTS](https://github.com/racai-ro/Ro-F5TTS) adapter
(samples-only as of 2026-05).

> **Critical safety contract:** The default backend image does NOT
> install torch / f5-tts / racai-ro weights. The provider stays
> `not_implemented` / `not_configured` until the operator explicitly
> opts in. No model is auto-downloaded. No fake Romanian audio is ever
> produced.

## What the F5TTS-Ro provider is

| Field | Value |
|---|---|
| Provider id | `f5tts_ro` |
| Label | F5TTS-Ro Romanian (optional service) |
| Backend type | `local_http_tts` |
| Architecture | Backend → HTTP wrapper service → F5-TTS Python API |
| CPU support | Yes (slow) |
| GPU support | Yes (rebuild wrapper on CUDA-capable host) |
| Network required | No (entirely local) |
| Model files required | Yes — operator-supplied |
| Reference voice required | Yes — operator-supplied WAV + transcript |

## Upstream repo audit

Audit performed 2026-05-16:

- **`racai-ro/Ro-F5TTS`** — public repo, no LICENSE file declared, 6.3 KB
  total. Contents: only `samples/` directory with WAV outputs (code
  switching, pronunciation, voice cloning). **No installable code, no
  Dockerfile, no requirements, no model weights.** The actual adapter
  is described in the paper [F5-TTS-RO: Extending F5-TTS to Romanian
  TTS via Lightweight Input Adaptation](https://arxiv.org/abs/2512.12297)
  (arXiv 2512.12297). The adapter is a ConvNeXt sub-network on top of
  the upstream F5-TTS frozen backbone.
- **Upstream `SWivid/F5-TTS`** — public, has a working PyPI package
  `f5-tts`, CLI entry point `f5-tts_infer-cli`, requires PyTorch and
  benefits from GPU. License: per the SWivid repo, F5-TTS itself is
  licensed under the CC BY-NC 4.0 (Non-Commercial). Operators are
  responsible for license compliance.

Re-audit performed 2026-05-17 (Phase 11F-CDOROB):

- **`cdorob/f5-tts-romanian`** — a public Hugging Face model with a
  **MIT license** (verified via `model_info().cardData['license']`).
  Files: `model_last.pt` (5.4 GB), `vocab.txt` (~14 KB), `README.md`,
  `.gitattributes`. README confirms it's an F5-TTS fine-tune trained
  on Common Voice 17 RO (35k samples) + datadriven-company/TTS-Romanian
  (50k samples), ~173 h total. Uses base model `F5TTS_v1_Base` with a
  character-based tokenizer. **This is the model the project ships
  with** as of Phase 11F-CDOROB.

Integration decision: wrap upstream F5-TTS in a separate Docker service
(`model-tts-ro`, profile `tts-ro`). The Dockerfile defaults to
`INSTALL_F5TTS=true` so the image actually generates Romanian audio out
of the box; build with `--build-arg INSTALL_F5TTS=false` for a
torch-free diagnostic-only image. The cdorob checkpoint is mounted
read-only from `models/tts/f5tts-ro/model/`.

## Architecture

```
+-------------------+      HTTP /tts/generate     +-----------------------+
|  backend (light)  | --------------------------> |  model-tts-ro service |
|  /api/v1/tts/...  | <-------------------------- |  fastapi + uvicorn    |
+-------------------+      JSON (no binary)       |  lazy torch + f5_tts  |
                                                  +-----------+-----------+
                                                              |
                                                              v
                                                  /models/f5tts-ro/
                                                  ├ checkpoint.pt        (operator)
                                                  └ reference/voice.wav  (operator)
                                                  └ reference/text.txt
```

The wrapper writes the synthesized WAV to a path the backend chooses
under its `UPLOAD_AUDIO_ROOT`, so the audio artifact lives on the same
volume as every other upload-intake artifact.

## Setup checklist

### 1. Decide CPU or GPU
The default wrapper image is CPU-only. For real-time inference,
rebuild the image on a CUDA-capable host and override
`F5TTS_RO_DEVICE=cuda`.

### 2. Place operator-supplied model + reference voice

```
mkdir -p models/tts/f5tts-ro/reference
# Drop the F5-TTS checkpoint(s) (operator-managed):
#   models/tts/f5tts-ro/<checkpoint>.pt or .safetensors
# Drop the racai-ro Romanian adapter weights (when available):
#   models/tts/f5tts-ro/adapter/<file>
# Reference voice for voice cloning:
cp /path/to/voice.wav     models/tts/f5tts-ro/reference/voice.wav
cp /path/to/transcript.txt models/tts/f5tts-ro/reference/text.txt
```

The wrapper refuses to start real inference if any of these are missing
and returns `assets_missing` from `/tts/generate`.

### 3. Build the wrapper image

```bash
make docker-tts-ro-build
```

The default image installs only `fastapi` + `uvicorn`. To install
upstream `f5-tts` + torch (heavy!) you currently need to rebuild the
image with the heavy ML layer — operator-decided, not automated by the
default Dockerfile. See `docker/model-tts-ro/Dockerfile` for the
extension point.

### 4. Start the optional service

```bash
make docker-tts-ro-up
```

The service is on profile `tts-ro` and is NOT started by the default
`make docker-light-up`. Once running, it listens on `localhost:8061`
(host) / `8080` (container).

### 5. Wire the backend

Add these to `.env` (or the per-shell env) before starting the backend:

```bash
F5TTS_RO_BASE_URL=http://aivideo-model-tts-ro-1:8080
F5TTS_RO_MODELS_ROOT=/models/f5tts-ro       # mount path inside backend
F5TTS_RO_DEFAULT_VOICE=ro_default
```

For host-side dev (backend not in Docker), use
`F5TTS_RO_BASE_URL=http://localhost:8061`.

Restart the backend container so the catalog reflects the new env:

```bash
BACKEND_PORT=8001 FRONTEND_PORT=3010 POSTGRES_PORT=5433 REDIS_PORT=6380 \
  NEXT_PUBLIC_API_BASE_URL=http://localhost:8001 \
  docker compose -f docker/compose.dev.yml up -d backend
```

### 6. Smoke test

```bash
make docker-tts-ro-smoke
```

Expected output when assets are not yet placed:

```json
{
  "service": "f5tts-ro",
  "status": "assets_missing",
  "ready": false,
  "details": {
    "runtime": {"torch_available": false, "f5_tts_available": false},
    "assets": {"models_root_exists": false, "weight_files_found": 0, ...}
  }
}
```

Once `torch` + `f5-tts` are installed in the wrapper image AND the
operator has placed weights + reference WAV under
`models/tts/f5tts-ro/`, the status flips to `ready`.

## Categorised error contract

`POST /api/v1/tts/generate` with `tts_provider_id=f5tts_ro` maps the
wrapper's responses to backend error codes:

| Wrapper status | Backend code | Operator action |
|---|---|---|
| `runtime_missing` (no torch/f5-tts) | `tts_runtime_missing` | Rebuild wrapper image with `torch` + `f5-tts` |
| `assets_missing` (no weights / no reference) | `tts_assets_missing` | Place files under `./models/tts/f5tts-ro/` |
| `config_missing` (env unset) | `tts_provider_not_configured` | Set `F5TTS_RO_BASE_URL` + restart backend |
| `generation_failed` | `tts_generation_failed` | Inspect wrapper logs: `make docker-tts-ro-logs` |
| Unreachable host | `tts_runtime_missing` | Start the service: `make docker-tts-ro-up` |
| `generated` + real WAV | 201 + `ArtifactType.audio` row | Audio plays in the UI; preview the file |

## License & legal

- Upstream F5-TTS: **CC BY-NC 4.0** (non-commercial). Operators using
  this provider commercially must seek an alternative license from
  Microsoft Research / SWivid.
- racai-ro/Ro-F5TTS: **No LICENSE file**. Treat as research-only until
  the authors publish terms.
- Reference voice: operator-supplied. Voice-cloning third parties
  without consent is prohibited; the form's `synthetic_or_owned_voice`
  flag remains load-bearing.

## Phase 20 — Multi-voice catalog

The provider catalog now reads `${F5TTS_RO_MODELS_ROOT}/voices.yaml`
and emits **one TTS dropdown row per voice** (instead of a single
`f5tts_ro` entry). Each voice declares:

- `id` — stable identifier (used as `f5tts_ro_<id>` provider_id)
- `label` — human-readable name shown in the dropdown
- `language` — ISO 639-1 code (`ro`); drives the per-language filter
- `gender` — `male` / `female` / `neutral`; drives the per-character filter
- `ref_audio` / `ref_text` — paths relative to `voices/<id>/`
- `sample_text` — short showcase phrase shown next to the voice
- `model` *(optional)* — voice-specific `model_*.pt` checkpoint. Omit
  to use the default `model/model_last.pt`.
- `description` *(optional)* — short note for the operator

### Adding a new voice

1. Drop the assets under
   `models/tts/f5tts-ro/voices/<voice_id>/`:
   - `ref_audio.wav` — short clean clip (5–15 s)
   - `ref_text.txt` — the EXACT transcript of the reference clip
   - `model.pt` *(optional)* — fine-tuned checkpoint when the voice
     has voice-specific weights
2. Append a YAML block to `voices.yaml`.
3. No code change, no container rebuild — the next
   `GET /api/v1/providers` reflects the new voice.

The voices currently shipped (Phase 20):

| `id` | Gender | Custom model? | Origin |
|------|--------|---------------|--------|
| `ro_default` | neutral | no (base) | cdorob upstream |
| `ro_barbat_1_linistit` | male | yes (95k steps) | NAS `Voce barbat linistita 1` |
| `ro_barbat_2_prezentator` | male | yes (125k steps) | NAS `Voce Barbat Prezentator 1` |
| `ro_barbat_3_costel` | male | no (base) | NAS `costel` |
| `ro_barbat_4_dorel` | male | no (base) | NAS `dorel` |
| `ro_barbat_5_georgel` | male | no (base) | NAS `georgel` |
| `ro_femeie_1_lacramioara` | female | no (base) | NAS `lacramioara` |
| `ro_femeie_2_marioara` | female | no (base) | NAS `marioara` |

### Sample audio endpoint

`GET /api/v1/providers/tts/f5tts_ro_<voice_id>/sample.wav` streams
the reference WAV the voice was trained against — the frontend
renders an inline `<audio controls>` element so the operator can
preview a voice before committing to a job.

### Per-voice request shape

When the operator picks a per-voice provider id the backend resolves
the catalog entry and adds three keys to the wrapper request body:

```json
{
  "text": "...",
  "voice_id": "ro_barbat_3_costel",
  "reference_audio_path": "/models/tts/f5tts-ro/voices/ro_barbat_3_costel/ref_audio.wav",
  "reference_text": "<contents of ref_text.txt>",
  "model_path": "/models/tts/f5tts-ro/voices/ro_barbat_1_linistit/model.pt"
}
```

`model_path` is only sent when the voice declares its own
checkpoint. The wrapper falls back to `F5TTS_RO_CKPT_FILE` when the
key is absent, so legacy (`f5tts_ro`) jobs keep working.

## Files added in Phase 10A-1

- `docker/model-tts-ro/Dockerfile` — optional service image
- `docker/model-tts-ro/server.py` — HTTP wrapper (`/health`,
  `/tts/generate`)
- `docker/model-tts-ro/requirements.txt` — fastapi + uvicorn only
- `docker/model-tts-ro/README.md` — service-local quickstart
- `docker/compose.dev.yml` — `model-tts-ro` service entry on profile
  `tts-ro`
- `backend/app/services/provider_registry.py` — `f5tts_ro` catalog
  entry
- `backend/app/api/tts.py` — `_generate_via_f5tts_ro()` HTTP router
- `frontend/components/CreateJobForm.tsx` — Romanian-specific operator
  guidance on `tts_*` errors when the F5TTS-Ro provider is selected
- `Makefile` — `docker-tts-ro-{build,up,down,logs,smoke}` targets
