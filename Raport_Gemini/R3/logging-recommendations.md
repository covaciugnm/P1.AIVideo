# Logging Recommendations & Standards

## 1. Backend Standards
- **Correlation ID:** Implement a `request_id` in a context var and include it in every log record.
- **Actor Attribution:** Every log emitted during an authenticated request MUST include the `user_id`.
- **Structured Mutation Logging:** For every POST/PATCH/DELETE, log: `actor_id`, `target_id`, `action`, `result`.
- **Security Audit:** Explicitly log security violations (401/403) with actor details if known.
- **Provider Performance:** Log duration for every external AI provider call.

## 2. Frontend Standards
- **User Intent:** Log major user actions (button clicks on forms, navigation) to the browser `logBus`.
- **Breadcrumbs:** Ensure `logBus` has enough "info" level entries to reconstruct a user session for debugging.
- **Consistent Error Reporting:** All failed API requests must emit a structured log to `logBus` including the logPath and status.

## 3. Redaction Standards
- **Sensitive Fields:** Never log values for: `password`, `value` (in secrets), `Authorization` header, `token`.
- **PII:** Be cautious with logging full names and emails unless necessary for the audit trail.

## 4. Implementation Priorities
1. **Remediate Auth Silence:** Add logs to `user_service.py` and `api/auth.py`.
2. **Inject user_id/request_id:** Update `log_buffer.py` and `main.py` middleware.
3. **Audit Admin Actions:** Add explicit logs to `api/users.py` for approval/suspension.
