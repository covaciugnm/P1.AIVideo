# Security audit logging — remediation report

## 1. Files changed
**Backend:** `models/security_audit.py` (NEW), `models/__init__.py`, `alembic/versions/0012_security_audit_events.py` (NEW), `services/security_audit_service.py` (NEW), `api/audit.py` (NEW), `api/auth.py` (login/register/change-password instrumented), `api/users.py` (approve/reject/suspend/reactivate/delete + protected-block instrumented), `api/secrets.py` (SECRET_LIST_VIEWED), `api/system.py` (BACKEND_LOGS_VIEWED), `core/security.py` (require_super_admin denial audit + request-id-aware), `main.py` (request-id middleware + X-Request-ID header + audit router).
**Frontend:** `lib/auth.ts` (LOGIN/REGISTER/LOGOUT breadcrumbs), `lib/users.ts` (USER_*_CLICKED breadcrumbs).
**Tests:** `tests/integration/test_phase_audit_logging.py` (NEW, 9 tests), `tests/integration/test_phase10c_api_surface.py` (audit route documented).

## 2. Migration revision id
`0012_security_audit` (revises `0011_users_auth`).

## 3. SecurityAuditEvent model
id, event_type, severity(info/warning/critical), result(success/failed/denied/blocked), actor_user_id/username/role, target_type/target_id, endpoint, method, request_id, ip_address, user_agent, reason, metadata_json, created_at. Indexed on event_type, severity, result, actor_user_id, target_type, target_id, request_id, created_at.

## 4. Request ID
`_request_id_and_log` middleware: reuses a sanitized inbound `X-Request-ID` or mints a uuid hex; sets `request.state.request_id`; echoes `X-Request-ID` response header; request start/end logs include `rid=`.

## 5. Auth logs
REGISTER_CREATED_PENDING / REGISTER_REJECTED_DUPLICATE_USERNAME / _EMAIL / _WEAK_PASSWORD; LOGIN_SUCCESS / LOGIN_FAILED / LOGIN_BLOCKED_{PENDING,SUSPENDED,REJECTED,DELETED}; PASSWORD_CHANGE_SUCCESS/FAILED. Failed login logs only the attempted username (never reveals existence; never logs the password).

## 6. User management logs
USER_APPROVED / USER_REJECTED / USER_SUSPENDED / USER_REACTIVATED / USER_SOFT_DELETED (+ `*_DENIED`), each with actor_user_id/username/role, target_id/target_username, old_status→new_status, old_role→new_role, reason. PROTECTED_SUPER_ADMIN_MODIFICATION_BLOCKED (severity=warning, result=blocked) when a protected-super-admin mutation is attempted.

## 7. Secrets / logs access audit
SECRET_LIST_VIEWED (success), SECRET_ACCESS_DENIED (denied — unauthenticated or insufficient role, via require_super_admin), BACKEND_LOGS_VIEWED (success), BACKEND_LOGS_ACCESS_DENIED (denied). No secret values are ever logged.

## 8. Frontend logBus events
LOGIN_SUBMIT/SUCCESS/FAILED, REGISTER_SUBMIT/SUCCESS_PENDING/FAILED, LOGOUT_CLICKED, USER_APPROVE_CLICKED/SUSPEND_CLICKED/DELETE_CLICKED. Username/ids only — never password/token.

## 9. Audit endpoint
`GET /api/v1/audit/security-events` (protected super admin) with filters: event_type, actor_user_id, target_type, target_id, result, severity, date_from, date_to, limit(≤500)/offset. Returns redacted events.

## 10. Redaction rules
`security_audit_service.redact()` masks any metadata key containing password/current_password/new_password/confirm/password_hash/token/access_token/authorization/secret/secret_value/api_key/jwt/bearer → `***REDACTED***` (recursive). Authorization headers / tokens / hashes / secret values are never captured. Verified by tests asserting the attempted password is absent from persisted events.

## 11. Curl verification proof (live, :8001)
```
GET /healthz                    → X-Request-ID: 9d5522d160f0411a991892f059776746
POST /auth/login (wrong creds)  → 401, audit LOGIN_FAILED ×1 (no password stored)
POST /auth/register log-test    → audit REGISTER_CREATED_PENDING ×1
POST /auth/login admin          → audit LOGIN_SUCCESS ×1
GET  /secrets (admin)           → audit SECRET_LIST_VIEWED ×1
GET  /system/logs/backend (admin)→ audit BACKEND_LOGS_VIEWED ×1
GET  /audit/security-events     → 6 events, request_id present, password leak = False
```

## 12. Test results
Backend: 9 new audit tests pass; full suite **952 passed, 12 skipped**.

## 13. Remaining risks
- Log retention policy not configured. No centralized logging/ELK. No SIEM export. No brute-force detection thresholds / lockout. No alerting on repeated failed logins or protected-super-admin modification attempts. Product-action audit (characters/jobs/uploads/images, Phase 8) only partially wired (auth/users/secrets/logs are the security-critical core covered here). Audit persistence shares the request DB session (extra commits) — acceptable but not a separate async sink.

## 14. Recommended next steps
Docker log rotation + retention; admin audit UI (read /audit/security-events); alert on N failed logins / on PROTECTED_SUPER_ADMIN_MODIFICATION_BLOCKED; export to SIEM; dedicated async audit sink; extend product-action coverage (Phase 8 events) consistently with request_id+user_id.
