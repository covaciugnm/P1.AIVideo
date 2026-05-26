# Remediation Plan for Claude

This plan lists items that require detailed knowledge of the project's security and lifecycle rules, and should be implemented by Claude.

## 1. Backend Security Logging (CRITICAL)
- **File:** `backend/app/core/security.py`
- **Functions:** `require_operator_or_above`, `require_active_user`.
- **Task:** Implement `log_access_denied` logic similar to `require_super_admin`.
- **Reason:** Viewer-level users attempting operator actions currently fail silently in the audit log.

## 2. Global user_id Attribution (HIGH)
- **File:** `backend/app/main.py` & `backend/app/core/log_buffer.py`.
- **Task:** Implement a mechanism to inject `user_id` into the logging context AFTER authentication is resolved in the middleware, and ensure the `log_buffer` captures it.
- **Reason:** Standard logs currently lack the "actor" identity.

## 3. Frontend Authentication Visibility (HIGH)
- **File:** `frontend/app/login/page.tsx` & `frontend/app/register/page.tsx`.
- **Task:** Emit `logBus` events for `LOGIN_SUBMITTED`, `LOGIN_SUCCESS`, `LOGIN_FAILED`.
- **Reason:** red-side panel is empty during login failures, forcing the operator to use browser DevTools.

## 4. Documentation Completion (MEDIUM)
- **Files:** `backend/app/services/user_service.py`, `backend/app/services/job_service.py`.
- **Task:** Add complete docstrings for all exported functions explaining invariants and role-based constraints.

## 5. Right Sidebar Audit Feed (MEDIUM)
- **File:** `backend/app/core/log_buffer.py`.
- **Task:** Include the `security.audit` logger in the capture loop.
- **Reason:** High-value security events should be visible to the Super Admin in the "Backend" sidebar tab.
