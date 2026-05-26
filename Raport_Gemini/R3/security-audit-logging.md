# Security Audit Logging Audit

| Event | Status | Redaction | Persisted? | Risk |
| :--- | :--- | :--- | :--- | :--- |
| **Failed Login** | NOT LOGGED | N/A | No | CRITICAL: Invisible brute force attempts. |
| **Successful Login** | NOT LOGGED | N/A | No | CRITICAL: No trail of who logged in and when. |
| **Secret Access** | NOT LOGGED | N/A | No | HIGH: Invisible credential harvesting. |
| **Secret Delete** | NOT LOGGED | N/A | No | HIGH: Unattributed sabotage. |
| **System Logs View**| NOT LOGGED | N/A | No | MEDIUM: Administrator information gathering. |
| **User Approved** | NOT LOGGED | N/A | No | HIGH: Unattributed authorization escalation. |
| **User Suspended** | NOT LOGGED | N/A | No | HIGH: Unattributed service denial. |
| **Upload Rejected** | LOGGED (STDOUT)| N/A | No | LOW: Captured in console. |
| **Auth Token Leaks** | SAFE | Yes | No | OK: No tokens found in logs. |
| **Password Leaks** | SAFE | Yes | No | OK: No passwords found in logs. |

### Classification

- **Unauthenticated Secrets Access:** `LOGGED BUT UNSAFE` (Middleware logs the IP/Path but not the intent or security violation context).
- **Directory Traversal:** `NOT LOGGED` (rejection is silent in logs).
- **Compliance Gates:** `PERSISTED AUDIT` (Compliance events are saved to the DB, which is good).

### Risk Summary
The primary security logging risk is the **silence of the auth and user management systems**. While "compliance" (business logic safety) is persisted in the database, "security" (who did what to whom) is almost entirely absent from the logs.
