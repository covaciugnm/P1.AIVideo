# Backend Function Logging Matrix (High Stakes)

| File | Function | External Input? | DB Write? | Logs Entry? | Logs Success? | Logs Error? | User ID? | Docstring? | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `api/auth.py` | `login` | YES | YES | No | NO* | NO* | No | YES | OK (via Audit) |
| `api/users.py` | `approve_user` | YES | YES | No | NO* | NO* | YES | NO | OK (via Audit) |
| `api/jobs.py` | `create_job` | YES | YES | YES | YES | No | No | NO | PARTIAL_LOGS |
| `api/secrets.py` | `delete_secret`| YES | YES | No | NO | No | No | NO | MISSING_LOGS |
| `api/system.py` | `get_backend_logs`| YES| No | No | YES* | No | YES | YES | OK (via Audit) |
| `services/user_service.py` | `register_user` | YES | YES | NO | NO | NO | No | NO | MISSING_LOGS |
| `services/job_service.py` | `create_job` | YES | YES | YES | YES | NO | No | NO | PARTIAL_LOGS |
| `services/character_image_service.py` | `generate_image` | YES | YES | YES | YES | YES | No | YES | OK |
| `core/security.py` | `require_super_admin` | No | No | No | No | YES* | No | YES | OK (via Audit) |
| `core/security.py` | `require_operator_or_above` | No | No | No | No | NO | No | YES | MISSING_LOGS |

*Note: "OK (via Audit)" means the function calls `security_audit_service` which handles structured logging and DB persistence. "NO*" indicates that standard logging is missing, but audit logging is present.*
