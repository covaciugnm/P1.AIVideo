# Docker Runtime Verification

Output of `docker compose -f docker/compose.dev.yml ps` confirms the following:

- `aivideo-backend-1` (aivideo-backend:latest): **Up (healthy)** on `0.0.0.0:8001->8000/tcp`. Verified via curl to `:8001/healthz`.
- `aivideo-frontend-1` (aivideo-frontend:latest): **Up (healthy)** on `0.0.0.0:3010->8010/tcp`. Verified via curl to `:3010` (returns 307).
- `aivideo-postgres-1` (postgres:16-alpine): **Up (healthy)** on `5433->5432`.
- `aivideo-redis-1` (redis:7-alpine): **Up (healthy)** on `6380->6379`.
- `aivideo-minio-1` (minio/minio:latest): **Up (healthy)** on `9000-9001`.
- `aivideo-model-ollama-1` (ollama/ollama:latest): **Up (healthy)** on `11435->11434`.
- `aivideo-cloudflared-1`: **Up (healthy)**.
- `aivideo-model-comfyui-1`, `aivideo-model-flux-1`, `aivideo-model-tts-ro-1`: **Up (healthy)**.

**Runtime Port Verification:**
- Backend port is verified as 8001.
- Frontend port is verified as 3010.

*Video generation runtime NOT VERIFIED*: The containers are up, but without the heavy model weights populated, actual GPU inference requests will fail (as evidenced by integration tests).
