# Final Action Plan (Prioritized)

## 1. BLOCKERS FOR DEPLOYMENT (CRITICAL)
- **Implement API Authentication:** Immediately add a FastAPI `Depends(verify_api_key)` or JWT middleware to protect ALL routes under `/api/v1/`, especially `/secrets` and `/system/logs`.
- **Remove Hardcoded Secrets:** Remove default fallbacks like `changeme` from Pydantic config. Force the application to crash on startup if `POSTGRES_PASSWORD` or `COMPLIANCE_SIGNING_KEY` are unset.

## 2. HIGH PRIORITY FIXES
- **Fix Local Pytest Environment:** Modify `conftest.py` to use a `tmp_path` fixture or override `ARTIFACTS_LOCAL_ROOT` dynamically during tests to prevent `/storage` PermissionErrors.
- **Mitigate Prompt Injection:** Introduce a Pydantic regex validator or a sanitization function for the `brief` payload before it hits the Ollama prompt template.

## 3. MEDIUM PRIORITY (Pre-Launch)
- **Add Frontend Test Suite:** Initialize `vitest` or `jest` and add foundational smoke tests for the primary forms (`CreateJobForm`, `CharacterForm`).
- **Fix Root UI Redirect:** Create an actual dashboard for `/app/page.tsx` instead of redirecting users to `/characters`, which produces a confusing initial user experience.
- **Update Documentation for Healthchecks:** Synchronize all runbooks and external monitoring tools to expect `/healthz` or `/api/v1/system/status` instead of `/api/health`.

## 4. LOW PRIORITY (Technical Debt)
- **Clean Up Stubs & Hardcoded English Errors:** Refactor provider stubs and remove hardcoded English exception strings (e.g., "unreachable: ollama daemon") in favor of translatable error codes.
