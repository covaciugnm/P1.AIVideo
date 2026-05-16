# Docker light runtime (Phase 4C)

The "light" runtime is the metadata-only stack: backend, orchestrator
(idle), frontend, postgres, and redis. It deliberately leaves out every
GPU container, every model service, and any dependency that would pull
torch / diffusers / SadTalker / Whisper / SDXL / ffmpeg. Bringing the
light stack up is the right way to exercise Phase 1–4B end-to-end (job
metadata flow, upload intake, dashboard polling, system status) without
touching CUDA.

## Prerequisites

- Docker Engine ≥ 24 with Docker Compose v2 (`docker compose version`).
- A copy of `.env` at the repo root:

  ```bash
  cp .env.example .env
  ```

  Every service in `docker/compose.dev.yml` references `../.env`. Without it
  the `make docker-light-*` targets refuse to run with a friendly error.

- The light stack does **not** need NVIDIA drivers, the Container Toolkit,
  or any model weights on disk.
- Phase 7C added the GPU readiness image (`Dockerfile.cuda` →
  `aivideo-agent-cuda:latest`) **only** behind `make docker-gpu-build` /
  `--profile gpu`. The light stack is unaffected — every `make
  docker-light-*` target still excludes `agent-voice` / `agent-face` /
  `agent-lipsync`. See [`gpu-runtime.md`](gpu-runtime.md) and
  [`sadtalker-runtime.md`](sadtalker-runtime.md).

## Services

| Service | Image | Role |
|---|---|---|
| `postgres` | `postgres:16-alpine` | Job + stage + artifact metadata. |
| `redis` | `redis:7-alpine` | Streams (no real worker reads them yet in Phase 4C). |
| `backend` | `aivideo-backend:latest` | FastAPI app. Serves `/healthz` + `/api/v1/*`. |
| `frontend` | `aivideo-frontend:latest` | Next.js dashboard (built statically into the image). |
| `orchestrator` | `aivideo-orchestrator:latest` | Phase 4C **idle** launcher — verifies every `agents.*` module imports, then sleeps. Real worker entrypoint lands later. |

The GPU agents (`agent-voice`, `agent-face`, `agent-lipsync`) and the
optional `model-llm` service live in `compose.dev.yml` too but are gated
behind `profiles: ["gpu"]`. A default `docker compose up` skips them.

## End-to-end check

The fastest way to verify the light stack works:

```bash
make docker-light-check
```

Which is shorthand for:

1. `make docker-config-check` — validates `compose.dev.yml`, `compose.prod.yml`, and `compose.dev.yml + compose.gpu.yml`.
2. `make docker-light-build` — builds only `backend`, `orchestrator`, and `frontend`.
3. `make docker-light-up` — starts `postgres`, `redis`, `backend`, `frontend`, `orchestrator`.
4. Waits for backend healthcheck + frontend HTTP.
5. `make docker-light-smoke` — curls `/healthz`, `/api/v1/system/status`, `/api/v1/jobs`, `/api/v1/stages`, `/` on the frontend.
6. `make docker-light-down` — stops the stack.

## Targeted commands

| Command | What it does |
|---|---|
| `make docker-config-check` | Three `docker compose … config` calls. No containers started. |
| `make docker-light-build` | Build images for `backend`, `orchestrator`, `frontend` only. Skips GPU. |
| `make docker-light-up` | Bring the light services up in detached mode. |
| `make docker-light-logs` | Tail logs from the five light services. |
| `make docker-light-smoke` | Curl backend + frontend endpoints once the stack is up. |
| `make docker-light-down` | `docker compose down`. |

## Storage volumes

Two named volumes back the upload + artifact roots:

- `inputs_data` → mounted read-write at `/storage/inputs` on `backend`, and read-only at `/storage/inputs` on `orchestrator`.
- `artifacts_data` → mounted read-write at `/storage/artifacts` on `backend`, read-only on `orchestrator`.

The defaults in `.env.example` for `UPLOAD_*_ROOT`, `PROVIDED_AUDIO_ALLOWED_ROOTS`, and `PROVIDED_IMAGE_ALLOWED_ROOTS` resolve under `/storage/inputs/...`, so upload + from-inputs work out of the box. Wipe local state with `docker volume rm aivideo_inputs_data aivideo_artifacts_data` (after a `make docker-light-down`).

## Networking

All services share the user-defined `aivideo` bridge network. From inside a container:

- `postgres` and `redis` are reachable on their service names + standard ports.
- `backend` and `frontend` are NOT routable from a browser via service names — Compose only publishes them on host ports `${BACKEND_PORT:-8000}` and `${FRONTEND_PORT:-3000}`. The frontend's `NEXT_PUBLIC_API_BASE_URL` is baked at build time and points at the **host** URL because the bundle runs in the browser, not in the frontend container.

## Intentionally NOT in the light runtime

- **No GPU services**, no CUDA base image pulled.
- **No SadTalker / MuseTalk / Wav2Lip / Whisper / SDXL** runtime.
- **No real video / audio / face / lip-sync rendering.**
- **No torch / diffusers / transformers / OpenCV / moviepy / ffmpeg** in any image.
- **No C2PA signing, no external publishing.**
- **No model weight downloads.** The `models/` directory is `.dockerignore`d.

## Troubleshooting

- **Frontend shows "Failed to load jobs — HTTP 404" or "Failed to fetch"** — two distinct causes:
  - **HTTP 404**: `NEXT_PUBLIC_API_BASE_URL` baked at build time still points at `:8000` while the stack runs on `:8001`. Fix: right sidebar → **Settings → Backend API Base URL** → set to `http://localhost:8001` → click **Test backend connection**. The override is persisted to `localStorage` and used on every subsequent API call without a rebuild.
  - **"Failed to fetch"** (Phase 4E fix): CORS preflight is being rejected because the backend doesn't allow your frontend's origin. The Phase 4E default `BACKEND_CORS_ORIGINS` covers `http://localhost:3000,http://localhost:3010,http://127.0.0.1:3000,http://127.0.0.1:3010`. If you have an older `.env`, regenerate: `cp .env.example .env` then restart the stack. To allow another origin, comma-extend `BACKEND_CORS_ORIGINS` in `.env`.
- **`env file …/.env not found`** — copy `.env.example` to `.env`.
- **`GET /api/v1/jobs` returns 500 with `column jobs.X does not exist`** — your Postgres volume predates a schema-changing phase. Phase 6B added Alembic, so prefer `docker exec aivideo-backend-1 alembic upgrade head` over `make docker-light-reset` (which still works but wipes all dev volumes). See [`db-migrations.md`](db-migrations.md).
- **Phase 4F+ TTS button always errors** — expected. `/api/v1/tts/generate` returns a categorised 503: `tts_runtime_missing` when `piper-tts` isn't installed, `tts_assets_missing` when voice files aren't on disk, `tts_provider_not_configured` when root env unset. See [`piper-runtime.md`](piper-runtime.md) to enable.
- **Phase 5B+ Generate Script returns 503** — `script_provider_disabled` means `SCRIPTWRITER_ENABLE_NETWORK_CALLS=false`; `script_provider_unreachable` means the Ollama daemon isn't reachable from inside the container. See [`ollama-scriptwriter.md`](ollama-scriptwriter.md).
- **Phase 4F MP3 upload fails with `audio_conversion_tool_missing`** — ffmpeg isn't installed in the running backend container. The light Docker image installs it via apt; if you've replaced the image with a custom one, add `apt install -y ffmpeg`.
- **Backend healthcheck never goes green** — the image lacks `curl` or `/healthz` is not responding. Check `make docker-light-logs` and confirm `uvicorn` started. The Dockerfile pins `curl` into the runtime stage.
- **Frontend 404s on `/jobs`** — `NEXT_PUBLIC_API_BASE_URL` was baked wrong at build time. Rebuild with `make docker-light-build` after editing `.env` (the compose file passes the value as a build arg).
- **`compose build` tries to download `nvidia/cuda:…`** — you ran `docker compose build` without naming services. Use `make docker-light-build` (which names only the light services) or pass an explicit list. The CUDA agents are profile-gated for `up`, but `build` with no args still resolves every service defined in the file.
- **`make docker-light-check` times out waiting for the frontend** — `next build` can take 30–60 s the first time and `next start` then needs another few seconds. Re-run smoke individually with `make docker-light-smoke` once `docker ps` shows everything `(healthy)`.
