# SadTalker Runtime — Phase 7B Readiness + Phase 10B Activation

This runbook covers the SadTalker video provider as it lands in Phase
7B: **hardened adapter + categorised readiness errors, no real
inference**. Real `torch.cuda` calls arrive in Phase 7D; this document
describes what is in place today, the env vars that gate it, the
six categorised error codes returned by `/api/v1/video/generate`, and
the explicit no-auto-download policy.

> **Phase 10B activation status (audited 2026-05-16):** real SadTalker
> MP4 generation is **blocked** on this host because (1) `nvidia-smi`
> reports `No devices were found`, and (2) every required SadTalker
> weight file under `models/lipsync/sadtalker/` is missing. The backend
> opt-in flags (`SADTALKER_ENABLE_REAL_INFERENCE=true` +
> `RUN_REAL_SADTALKER=1`) are now wired through `docker/compose.dev.yml`
> so that flipping them in the shell surfaces categorised error codes
> (`video_assets_missing` / `video_runtime_missing` / `video_gpu_missing`)
> instead of the legacy `provider_not_implemented`. No fake MP4 is
> registered under any combination of these flags.

## How to activate real SadTalker (Phase 10B operator checklist)

Five gates must all pass before `/api/v1/video/generate` can produce a
real MP4. Each gate has its own categorised error code; the API never
guesses or fakes when a gate fails.

| Gate | Verification | Failure code |
|---|---|---|
| 1. NVIDIA GPU visible on host | `nvidia-smi` lists at least one device | `video_gpu_missing` |
| 2. NVIDIA Container Toolkit installed | `make docker-gpu-smoke` reports `nvidia-smi` inside container | `video_gpu_missing` |
| 3. GPU image built with torch + SadTalker | `make docker-gpu-build` (uses `docker/agents/Dockerfile.cuda`) | `video_runtime_missing` |
| 4. All 5 weight files under `${SADTALKER_MODELS_ROOT}` | `make docker-gpu-smoke` or `find ./models/lipsync/sadtalker/` | `video_assets_missing` |
| 5. Operator opt-in flags set | `SADTALKER_ENABLE_REAL_INFERENCE=true RUN_REAL_SADTALKER=1` | `provider_not_implemented` (legacy) |

Start command (after every gate is green):

```bash
SADTALKER_ENABLE_REAL_INFERENCE=true RUN_REAL_SADTALKER=1 \
  SADTALKER_MODELS_ROOT=/models/lipsync/sadtalker \
  BACKEND_PORT=8001 FRONTEND_PORT=3001 POSTGRES_PORT=5433 REDIS_PORT=6380 \
  NEXT_PUBLIC_API_BASE_URL=http://localhost:8001 \
  docker compose -f docker/compose.dev.yml \
                 -f docker/compose.gpu.yml \
                 --profile gpu up -d agent-lipsync
```

The default light backend now mounts `./models:/models:ro` so the
readiness probe inside the backend container can see whatever weight
files the operator drops on the host without rebuilding.



> **Phase 7B does not run real SadTalker inference.** Even with both
> opt-in flags on (`SADTALKER_ENABLE_REAL_INFERENCE=true` +
> `RUN_REAL_SADTALKER=1`), the adapter's `generate()` method returns
> `not_implemented`. Phase 7D ships the actual call. This is
> deliberate — it lets us validate the readiness surface, error
> categorisation, and operator UX before any GPU code runs.

## 1. Required files (place manually — we do NOT auto-download)

SadTalker needs five files under `${SADTALKER_MODELS_ROOT}`:

```
${SADTALKER_MODELS_ROOT}/
├── checkpoints/
│   ├── mapping_00109-model.pth.tar
│   ├── mapping_00229-model.pth.tar
│   ├── SadTalker_V0.0.2_256.safetensors
│   └── SadTalker_V0.0.2_512.safetensors
└── gfpgan/
    └── GFPGANv1.4.pth
```

Get the weights from the upstream releases:

- SadTalker checkpoints: <https://github.com/OpenTalker/SadTalker/releases>
- GFPGAN v1.4: <https://github.com/TencentARC/GFPGAN/releases>

Place them under `SADTALKER_MODELS_ROOT` (the path you set in `.env`).
**This repo does not download model weights from any script, install
target, container build, or runtime call.** That is policy, not
convenience — see `ALLOW_MODEL_AUTODOWNLOAD=false` in `.env.example`
and the Phase 7B test `test_sadtalker_provider_module_has_no_download_calls`.

License terms for SadTalker weights and GFPGAN apply. Review them before
using the provider in production.

## 2. Env vars

```bash
# Where the weights live. Resolved in this order:
#   1. SADTALKER_MODELS_ROOT (preferred)
#   2. LIPSYNC_MODELS_ROOT/sadtalker (fallback)
SADTALKER_MODELS_ROOT=/models/lipsync/sadtalker

# Two-flag gate. BOTH must be on before any phase runs real inference.
# Phase 7B refuses even when both are on — Phase 7D ships the actual
# torch.cuda call. Default: real inference disabled.
SADTALKER_ENABLE_REAL_INFERENCE=false
RUN_REAL_SADTALKER=0

# Selected video provider for /api/v1/video/generate when no explicit
# provider_id is sent. The catalog still exposes every provider.
VIDEO_PROVIDER=sadtalker

# Optional explicit overrides. Unset → reads from SADTALKER_MODELS_ROOT.
SADTALKER_CHECKPOINT_PATH=
SADTALKER_CONFIG_PATH=

# Pinned in .env.example. Do not flip without a compliance review.
ALLOW_MODEL_AUTODOWNLOAD=false
```

## 3. Check provider status

```bash
# Full catalog — sadtalker row carries live readiness notes + docs_url.
curl -s http://localhost:8000/api/v1/providers/video-generators | jq '.[] | select(.provider_id=="sadtalker")'

# Detail endpoint:
curl -s http://localhost:8000/api/v1/providers/video_generator/sadtalker | jq
```

Expected fields on the sadtalker row:

| Field | Phase 7B value |
|---|---|
| `category` | `video_generator` |
| `status` | `not_implemented` (until Phase 7D) |
| `requires_gpu` | `true` |
| `requires_model_files` | `true` |
| `healthcheck_available` | `true` (we have `inspect_status()`) |
| `docs_url` | path to this runbook |
| `notes` | live readiness string describing the current state |

## 3b. Phase 7C: GPU image readiness (no real inference yet)

Phase 7C ships the GPU image `aivideo-agent-cuda:latest`:

```bash
# Lean: CUDA + Python + ffmpeg + common/agents wheels (~4.5 GB, no torch)
make docker-gpu-build

# Torch-capable (~6–7 GB, required for Phase 7D)
INSTALL_TORCH=true make docker-gpu-build

# Tear down the GPU-profiled services (leaves the light stack running)
make docker-gpu-down
```

`docker/compose.gpu.yml` now puts SadTalker-specific env on
`agent-lipsync` (still gated behind `--profile gpu` — never in the
default light stack):

```yaml
agent-lipsync:
  <<: *gpu-one
  environment:
    VIDEO_PROVIDER: ${VIDEO_PROVIDER:-sadtalker}
    SADTALKER_MODELS_ROOT: /models/lipsync/sadtalker
    SADTALKER_ENABLE_REAL_INFERENCE: "${SADTALKER_ENABLE_REAL_INFERENCE:-false}"
    RUN_REAL_SADTALKER: "${RUN_REAL_SADTALKER:-0}"
    ALLOW_MODEL_AUTODOWNLOAD: "false"
  volumes:
    - ../models/lipsync/sadtalker:/models/lipsync/sadtalker:ro
```

Weights mount **read-only** (`:ro`). The container cannot mutate them.

## 4. Categorised error codes

`/api/v1/video/generate` with `provider_id="sadtalker"` always returns
HTTP 200 with a structured `VideoGenerationResult`. The `error_code`
field is the categorisation operators / frontend pattern-match on:

| `error_code` | When it fires | What to fix |
|---|---|---|
| `provider_not_implemented` | Default state: real-inference flags off, or all gates open and we deliberately refuse to invoke the real path (Phase 7B). | Wait for Phase 7D, or flip both flags + supply weights to see the next category. |
| `video_provider_not_configured` | Gate open but `SADTALKER_MODELS_ROOT` is unset and no `LIPSYNC_MODELS_ROOT` fallback. | Set `SADTALKER_MODELS_ROOT` in `.env`. |
| `video_assets_missing` | Gate open, root set, but weights aren't on disk. | Place the five files listed in §1. |
| `video_runtime_missing` | Gate open, assets present, but `torch` isn't importable in the current image. | The default light backend is intentionally torch-free; run SadTalker from the GPU image (`Dockerfile.cuda` — Phase 7C). |
| `video_gpu_missing` | Gate open, torch present, but no CUDA device visible. | Install / fix NVIDIA driver + Container Toolkit (`make docker-gpu-smoke`); see [`gpu-runtime.md`](gpu-runtime.md). |
| `video_generation_failed` | Reserved for Phase 7D when real inference is wired and throws. | Phase 7B never returns this — it can only appear once Phase 7D lands. |

The response shape is metadata-only — no binary content, no base64
blob, no `data:video` URI. `output_video_artifact_id` is `null` for
every Phase 7B response.

## 4b. Phase 7D: enabling real inference (opt-in only)

Phase 7D wires the real `SadTalkerProvider.generate()` path. All
**seven** gates must be satisfied or the call short-circuits to a
categorised error:

| # | Gate | Where checked | Failure code |
|---|---|---|---|
| 1 | `SADTALKER_ENABLE_REAL_INFERENCE=true` | `_real_inference_enabled()` | `video_provider_not_implemented` |
| 2 | `RUN_REAL_SADTALKER=1` | `_real_inference_enabled()` | `video_provider_not_implemented` |
| 3 | `SADTALKER_MODELS_ROOT` set + weights on disk | `inspect_assets()` | `video_assets_missing` / `video_provider_not_configured` |
| 4 | `torch` importable | `inspect_runtime()` | `video_runtime_missing` |
| 5 | CUDA device visible | `inspect_gpu()` | `video_gpu_missing` |
| 6 | Input image path readable | `generate()` | `video_generation_failed` |
| 7 | Input audio path readable | `generate()` | `video_generation_failed` |

If all seven pass, `_attempt_real_inference()` runs SadTalker and the
API registers the resulting MP4 as an `ArtifactType.video` row.

To enable real inference end-to-end:

```bash
# 1. Build the GPU image with the heavy deps.
INSTALL_TORCH=true INSTALL_SADTALKER_DEPS=true make docker-gpu-build

# 2. Place SadTalker weights under SADTALKER_MODELS_ROOT (see §1).

# 3. Set the env vars in .env (or per-shell):
export SADTALKER_ENABLE_REAL_INFERENCE=true
export RUN_REAL_SADTALKER=1
export SADTALKER_MODELS_ROOT=/models/lipsync/sadtalker

# 4. Run the GPU-profile stack:
docker compose -f docker/compose.dev.yml -f docker/compose.gpu.yml --profile gpu up -d

# 5. Hit /api/v1/video/generate as usual.
```

### Opt-in real smoke test

```bash
RUN_REAL_SADTALKER_SMOKE=1 \
SADTALKER_ENABLE_REAL_INFERENCE=true \
RUN_REAL_SADTALKER=1 \
SADTALKER_MODELS_ROOT=/path/to/weights \
make phase7d-test
```

Without `RUN_REAL_SADTALKER_SMOKE=1`, the real-runtime smoke test
auto-skips. The default `make test` never invokes real inference.

### What success looks like

The API response when generation completes:

```json
{
  "status": "completed",
  "provider_id": "sadtalker",
  "model_id": "sadtalker-v1",
  "job_id": "…",
  "output_video_artifact_id": "<uuid>",
  "message": "SadTalker inference completed.",
  "metadata": {
    "video_uri": "file:///storage/artifacts/video/<job>/sadtalker_…mp4",
    "video_size_bytes": 7_345_120,
    "video_checksum_sha256": "…",
    "target_duration_seconds": 30,
    "audio_duration_seconds": 28.4
  }
}
```

The MP4 is registered as `ArtifactType.video` with `mime_type=video/mp4`,
checksum, size, optional `duration_seconds` / `width` / `height` (when
SadTalker reports them). The frontend's existing artifact table renders
it without changes.

### Cleanup contract

If `_attempt_real_inference()` raises after producing a partial MP4,
the file is unlinked before the categorised failure is returned. **No
phantom artifact is registered** for failed runs — the API tests pin
this invariant explicitly.

## 5. How real inference will be enabled (preview of Phase 7D)

The Phase 7B adapter sets up everything **except** the actual
torch.cuda call:

```text
+---------------------------+
|     /api/v1/video/        |
|        generate           |
+-------------+-------------+
              |
              v
+---------------------------+
|  SadTalkerProvider        |
|    .inspect_status()      |  ← Phase 7B (this phase)
|    .generate() stub       |
+-------------+-------------+
              |
              v   <— Phase 7D flips this edge on
+---------------------------+
|  torch.cuda inference     |
|  +  GFPGAN restore        |
|  +  PCM-WAV → MP4         |
+---------------------------+
```

Phase 7D will replace the `generate()` body's `return not_implemented`
with the actual call **only when** both flags are on, weights are
present, torch is importable, and CUDA is visible. Until then, the
adapter remains a categorised readiness surface.

## 6. What is **not** in scope for Phase 7B

- Building the GPU image. The CUDA Dockerfile stays a stub.
- Downloading any weights.
- Adding `torch` to `backend/pyproject.toml` or the `agents` base wheel.
- Running real SadTalker. Even with all flags on, `generate()` returns
  `not_implemented`.
- Wiring the SadTalker output into the editor / publisher pipeline
  (Phase 7E).
- C2PA signing of generated MP4s (later phase).

## 6b. Phase 8A: video artifact preview + download

The Job Detail page renders a Video preview card whenever a job has
any artifact with ``artifact_type=video``. The browser fetches bytes
from ``/api/v1/artifacts/{id}/content`` (now in the serve allow-list).
A Download button hits the same endpoint with ``?download=true`` —
the Content-Disposition becomes ``attachment; filename="artifact-<short-id>.mp4"``
and the raw on-disk path is never echoed in headers.

If your browser cannot decode the file, the ``<video>`` fallback
``<p>`` points users at the same Download URL.

## 7. Frontend behavior

The Settings panel + per-job form already let operators select
SadTalker as the video provider (Phase 6D). Phase 7B doesn't change
the UI; it changes what the backend reports when the operator hits
"generate":

- Default install → "Provider not implemented yet" message.
- Operator opted in but missing assets → "Weights not on disk" + the
  five missing paths.
- Operator opted in + assets present + no GPU → "No CUDA device
  visible" + link to `gpu-runtime.md`.

All three reach the user as the existing `error_code` field; no UI
work is required to surface them.

## 8. Test coverage

`make phase7b-test` runs 19 invariants. Highlights:

- Module-load isolation: importing the SadTalker provider does **not**
  pull torch / diffusers / transformers / opencv / sadtalker into
  `sys.modules`.
- Default-state Phase 6A compatibility: `provider_not_implemented`.
- Each categorised error code reachable with the documented env-var
  flip.
- `ALLOW_MODEL_AUTODOWNLOAD=false` pinned in `.env.example`.
- Provider source contains no `urllib.request` / `requests.get` /
  `huggingface_hub.snapshot_download` / `wget` / `curl ` calls.
- `app.api.video` does not pull torch into `sys.modules` at import.

Run with: `make phase7b-test` (also rolled into `make test`).
