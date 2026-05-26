# UI Action Log Panel Matrix

| Action Group | Action | Frontend logBus? | Backend Logs? | Right Panel (Front)? | Right Panel (Back)? | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Auth** | Login Success | NO | Audit Only | NO | NO* | PARTIAL |
| **Auth** | Login Fail | NO | Audit Only | NO | NO* | PARTIAL |
| **Users** | Approve User | NO | Audit Only | NO | NO* | PARTIAL |
| **Characters** | Create Character | NO | YES | NO | YES | PARTIAL |
| **Images** | Generate Image | YES | YES | YES | YES | OK |
| **Jobs** | Create Job | YES | YES | YES | YES | OK |
| **Settings** | Update Settings | YES | NO | YES | NO | PARTIAL |
| **Secrets** | Delete Secret | NO | NO | NO | NO | MISSING |

*Note: "Audit Only" events in the backend are log entries, but if the `log_buffer` doesn't capture the `security.audit` logger correctly or if they are not emitted as standard INFO/WARNING, they might not show up in the "Backend" tab of the sidebar. In `log_buffer.py`, all loggers under "app" are captured. `security.audit` is a top-level logger, so it is NOT captured by the sidebar currently.*
