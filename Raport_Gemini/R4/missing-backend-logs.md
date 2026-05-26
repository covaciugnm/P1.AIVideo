# Missing Backend Logs

The following critical or high-stake backend functions are missing explicit logging or audit events:

## 1. Security & Admin (CRITICAL)
- `backend/app/core/security.py`: `require_operator_or_above` and `require_active_user` do not log access denials (unlike `require_super_admin`).
- `backend/app/api/secrets.py`: `delete_secret` is silent. No audit event for credential removal.
- `backend/app/api/users.py`: Listing users (`list_users`, `list_pending`) is not logged as an audit event.

## 2. Business Logic (HIGH)
- `backend/app/services/user_service.py`: `register_user`, `approve`, `suspend`, `soft_delete` lack internal `logger.info` calls (though the API layer catches some via Audit).
- `backend/app/api/characters.py`: Updating character status is logged in API but not in the service layer where the state transition actually happens.
- `common/path_safety.py`: `_validate_local_path` raises `ValueError` on traversal/safety violation but doesn't log the event. This is a missed signal for security monitoring.

## 3. Operations (MEDIUM)
- `backend/app/services/job_service.py`: `set_job_status` is silent. Terminal job states (failed/published) should be logged at the service level for better traceability in multi-agent flows.
- `backend/app/api/jobs.py`: `list_jobs` is silent.
