# 02 — Docker / runtime

Compose: `docker/compose.dev.yml` invoked with `--env-file .env`. `docker compose config` → **VALID**.

## Running containers (evidence: `docker compose ps`)
| Container | Status | Host port → container |
|---|---|---|
| aivideo-backend-1 | Up (healthy) | **8001 → 8000** |
| aivideo-frontend-1 | Up (healthy) | **3010 → 8010** (also 3000 internal) |
| aivideo-postgres-1 | Up (healthy) | 5433 → 5432 |
| aivideo-redis-1 | Up (healthy) | 6380 → 6379 |
| aivideo-minio-1 | Up (healthy) | 9000-9001 |
| aivideo-model-comfyui-1 | Up (healthy) | **8066 → 8188** |
| aivideo-model-flux-1 | Up (healthy) | 8064 → 8080 |
| aivideo-model-ollama-1 | Up (healthy) | 11435 → 11434 |
| aivideo-model-tts-ro-1 | Up (healthy) | 8061 → 8080 |
| aivideo-model-llm-1 | Up | — |
| aivideo-cloudflared-1 | Up (healthy) | — |

> **Ports differ from the audit-brief assumptions** (brief assumed backend :8000 / frontend :5173). Actual: backend **:8001**, frontend **:3010**. The brief's `curl :8000` / `curl :5173` would FAIL — use :8001 / :3010.

## NOT running (evidence: `docker ps | grep -E 'orchestrator|agent-'`)
- `aivideo-orchestrator-1` — **STOPPED**
- `aivideo-agent-{voice,face,lipsync,scriptwriter,editor,qc,publisher,compliance}-1` — **ALL STOPPED**
- (An `ai-home-orchestrator` is running but belongs to a DIFFERENT compose project — not P1.AIVideo.)
- → **Video/DAG pipeline is non-operational at runtime.** Intentional (move to 128 GB box).

## Connectivity verified
- `curl :8001/healthz` → `{"status":"ok","phase":"1","scope":"metadata-only"}`
- `curl :8001/api/v1/system/status` → `database_reachable: true`
- backend → ComfyUI: `urllib.urlopen('http://aivideo-model-comfyui-1:8188/system_stats')` → **200**
- `curl :3010/characters` → **HTTP 200**

## ComfyUI service (model-comfyui)
- Image `aivideo-model-comfyui:latest` (26.1 GB) built; ComfyUI **v0.21.1** running.
- Volumes (resolved): `models/image/sdxl/sdxl-base-1.0 → /comfyui/models/checkpoints/sdxl-base-1.0:ro`, `models/image/flux`, `models/image/sd35`, `artifacts_data → /comfyui/output`.
- **Missing mounts for InstantID:** no `custom_nodes` mount, no instantid/controlnet/insightface model mounts. `custom_nodes` inside container = only `example_node.py.example` + `websocket_image_save.py`.
- GPU: 24 GB total, ~23.6 GB free at audit. SDXL checkpoint visible to ComfyUI (`/object_info/CheckpointLoaderSimple` lists `sdxl-base-1.0/sd_xl_base_1.0.safetensors`).

## F5 TTS shared-volume fix (verified)
Raw compose `agent-voice`/`agent-face`/`agent-lipsync` now carry `inputs_data:/storage/inputs` + `artifacts_data:/storage/artifacts` + `<<: *agent-runtime-env` (evidence: awk extract of the agent-voice block). Fix is **in the compose file**; agents are currently stopped so not exercised at runtime.

## Backend volume for workflows
`backend` mounts `/home/cesiro/Documents/P1.AIVideo/workflows → /workflows` (ro). `COMFYUI_WORKFLOW_DIR=/workflows/comfyui` (corrected during the session; templates resolve).
