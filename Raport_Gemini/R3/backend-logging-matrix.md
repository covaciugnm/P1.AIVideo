# Backend Logging Matrix

| Endpoint | Method | Purpose | Receive Logged? | Success Logged? | Fail Logged? | Audit? | Identifiers | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `/healthz` | GET | Health | No | No | No | No | None | OK (Skipped by design) |
| `/api/v1/auth/register` | POST | Register | Middleware | No | Middleware | No | None | PARTIAL |
| `/api/v1/auth/login` | POST | Login | Middleware | No | Middleware | No | None | PARTIAL |
| `/api/v1/auth/me` | GET | Me | No | No | No | No | user_id | MISSING |
| `/api/v1/users` | GET | List Users | No | No | No | No | actor_id | MISSING |
| `/api/v1/users/{user_id}/approve` | POST | Approve | Middleware | No | Middleware | No | actor/target_id | MISSING |
| `/api/v1/jobs` | GET | List Jobs | No | No | No | No | None | MISSING |
| `/api/v1/jobs` | POST | Create Job | Yes (API) | Yes (API) | Middleware | No | job_id | OK |
| `/api/v1/jobs/{job_id}` | PATCH | Update Job | Yes (API) | Yes (API) | Yes (API) | No | job_id | OK |
| `/api/v1/jobs/{job_id}` | DELETE | Delete Job | Yes (API) | Yes (API) | Yes (API) | No | job_id | OK |
| `/api/v1/secrets` | GET | List Secrets | No | No | No | No | None | MISSING |
| `/api/v1/secrets` | POST | Upsert Secret | Yes (API) | Yes (API) | Middleware | No | key_name | OK |
| `/api/v1/system/status` | GET | Status | No | No | No | No | None | OK (Metadata) |
| `/api/v1/system/logs/backend` | GET | Logs | No | No | No | No | actor_id | MISSING |
| `/api/v1/characters` | GET | List Char | No | No | No | No | None | MISSING |
| `/api/v1/characters` | POST | Create Char | Yes (API) | Yes (API) | Middleware | No | character_id | OK |
| `/api/v1/uploads/image` | POST | Upload | Yes (API) | Yes (API) | Yes (API) | No | artifact_id | OK |

*Note: Middleware captures all POST/PATCH/DELETE start/end, but often lacks business identifiers like character_id unless the API handler also logs it.*
