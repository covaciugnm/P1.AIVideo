# Gemini Claims Verification Table

| Gemini Claim | Confirmed? | Evidence | Correction if needed | Severity | Blocks demo? | Blocks production? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Backend lacks authentication** | CONFIRMED | `grep` shows no Auth/JWT/Security dependencies on any `APIRouter` or endpoint in `backend/app`. | N/A | CRITICAL | Yes (if external) | Yes |
| **Anyone can access logs/secrets** | CONFIRMED | `/api/v1/system/logs/backend` and `/api/v1/secrets/*` have no authentication middleware. | N/A | CRITICAL | Yes (if external) | Yes |
| **Backend tests: 60 fail out of 938** | CONFIRMED | Pytest output: `60 failed, 866 passed, 12 skipped`. | Total is 938. | HIGH | No | Yes |
| **Failures caused by /storage permissions** | CONFIRMED | Pytest stack traces show `PermissionError: [Errno 13] Permission denied: '/storage'`. | N/A | HIGH | No | Yes |
| **Frontend has no npm test script** | CONFIRMED | `cat frontend/package.json` shows scripts for dev, build, start, lint, typecheck. No `test`. | N/A | MEDIUM | No | Yes |
| **Prompt injection risk** | CONFIRMED | Checked `agents/scriptwriter/providers/ollama/provider.py`, `req.brief` is directly injected via f-string. | N/A | HIGH | No | Yes |
| **Hardcoded default secrets** | CONFIRMED | `backend/app/core/config.py` lines 42 and 65 contain `changeme` and `phase2-noop-changeme`. | N/A | HIGH | No | Yes |
| **Root / redirects to /characters** | CONFIRMED | `curl -I http://localhost:3010/` returns `307 Temporary Redirect` | N/A | LOW | No | No |
| **/api/health mismatch** | CONFIRMED | `curl http://localhost:8001/healthz` works. `/api/health` 404s. | N/A | LOW | No | No |
| **All 11 docker services start correctly** | CONFIRMED | `docker compose ps` shows 11 services `Up (healthy)`. | N/A | NONE | No | No |
