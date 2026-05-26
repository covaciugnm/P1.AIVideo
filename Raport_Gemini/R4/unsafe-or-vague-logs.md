# Unsafe or Vague Logs

The following log messages were identified as problematic:

| Source | File | Log Message / Call | Issue Type | Risk |
| :--- | :--- | :--- | :--- | :--- |
| Backend | `app/api/jobs.py` | `logger.info("jobs.create_endpoint.start ...")` | TOO_VAGUE | Missing `user_id` of the requester. |
| Backend | `services/character_image_service.py`| `logger.info("characters.generate_image.start ...")` | TOO_VAGUE | Missing `user_id`. |
| Backend | `app/main.py` | `_request_logger.info("request.start %s %s rid=%s", ...)` | TOO_VAGUE | Missing `user_id`. (Middleware runs before auth). |
| Frontend | `lib/api.ts` | `${method} ${logPath} → ${response.status}` | OK | Redaction happens in backend, frontend logs are safe. |

## 1. Vague Attribution
The primary issue in the project is **Vague Attribution**. While events are logged, the "actor" (the user who performed the action) is often missing from standard application logs, requiring complex joins with the security audit DB table to reconstruct a timeline.

## 2. Leakage Verification
No instances of hardcoded secrets or raw passwords were found in log strings. The project correctly uses placeholders and `security_audit_service.redact()` for sensitive fields.
