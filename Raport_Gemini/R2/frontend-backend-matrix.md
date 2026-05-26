# Frontend-Backend API Connection Matrix

Built from code search in `frontend/lib/api.ts` and `frontend/lib/characters.ts`:

| Frontend API Call | Backend Endpoint | Matches OpenAPI? | Status |
| :--- | :--- | :--- | :--- |
| `getSystemStatus` | `GET /api/v1/system/status` | Yes | **OK** |
| `getBackendLogs` | `GET /api/v1/system/logs/backend` | Yes | **OK** |
| `getJobs` | `GET /api/v1/jobs` | Yes | **OK** |
| `getJobDetail` | `GET /api/v1/jobs/{jobId}` | Yes | **OK** |
| `createJobFromInputs` | `POST /api/v1/jobs/from-inputs` | Yes | **OK** |
| `uploadText` | `POST /api/v1/uploads/text` | Yes | **OK** |
| `uploadAudio` | `POST /api/v1/uploads/audio` | Yes | **OK** |
| `uploadImage` | `POST /api/v1/uploads/image` | Yes | **OK** |
| `getProviders` | `GET /api/v1/providers` | Yes | **OK** |
| `generateScript` | `POST /api/v1/script/generate` | Yes | **OK** |
| `generateTTS` | `POST /api/v1/tts/generate` | Yes | **OK** |
| `generateVideo` | `POST /api/v1/video/generate` | Yes | **OK** |
| `getCharacters` | `GET /api/v1/characters` | Yes | **OK** |
| `getCharacterLookups`| `GET /api/v1/characters/lookups` | Yes | **OK** |
| `Health check ping` | `GET /healthz` | Yes | **OK** |

**Conclusion:** The API contracts are strictly defined and matched perfectly between the frontend Typescript interfaces and the FastAPI backend OpenAPI specification.
