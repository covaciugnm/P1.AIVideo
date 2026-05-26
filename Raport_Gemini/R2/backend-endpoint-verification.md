# Backend Endpoint Verification

Extracted directly from `http://localhost:8001/openapi.json` and verified against the running container:

- `/healthz` : `['get']` - **VERIFIED OK** (Returns 200 JSON with phase and scope)
- `/api/v1/system/status` : `['get']` - **VERIFIED OK** (Returns 200 system stats)
- `/api/v1/system/technical-architecture` : `['get']` - **VERIFIED OK**
- `/api/v1/system/technical-architecture.md` : `['get']` - **VERIFIED OK**
- `/api/v1/system/logs/backend` : `['get']` - **VERIFIED (CRITICAL VULNERABILITY)**: Completely unauthenticated.
- `/api/v1/jobs` : `['get', 'post']` - **VERIFIED OK**
- `/api/v1/jobs/{job_id}/*` : `['get', 'patch', 'delete', 'post']` - **VERIFIED OK**
- `/api/v1/uploads/text` : `['post']` - **VERIFIED OK**
- `/api/v1/uploads/audio` : `['post']` - **VERIFIED OK**
- `/api/v1/uploads/image` : `['post']` - **VERIFIED OK**
- `/api/v1/jobs/from-inputs` : `['post']` - **VERIFIED OK**
- `/api/v1/settings/ui` : `['get', 'patch']` - **VERIFIED OK**
- `/api/v1/providers` : `['get']` - **VERIFIED OK**
- `/api/v1/tts/generate` : `['post']` - **VERIFIED OK**
- `/api/v1/script/generate` : `['post']` - **VERIFIED OK**
- `/api/v1/video/generate` : `['post']` - **VERIFIED OK**
- `/api/v1/characters` : `['get', 'post']` - **VERIFIED OK**
- `/api/v1/characters/{character_id}/images/generate-initial` : `['post']` - **VERIFIED OK**
- `/api/v1/characters/{character_id}/images/generate-consistent` : `['post']` - **VERIFIED OK**
- `/api/v1/secrets` : `['get', 'post']` - **VERIFIED (CRITICAL VULNERABILITY)**: Unauthenticated.
- `/api/v1/secrets/{key_name}` : `['put', 'delete']` - **VERIFIED (CRITICAL VULNERABILITY)**: Unauthenticated.

*Note: All endpoints are structurally sound according to OpenAPI, but universally lack Authentication/Authorization mechanisms.*
