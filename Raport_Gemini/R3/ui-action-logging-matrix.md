# UI Action Logging Matrix

| Action Group | Action | Frontend success/fail? | Backend Log? | Security Audit? | actor_id? | target_id? | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Auth** | Login | Yes | Middleware Only | No | No | No | MISSING |
| **Auth** | Register | Yes | Middleware Only | No | No | No | MISSING |
| **Users** | Approve | Yes | Middleware Only | No | No | No | MISSING |
| **Users** | Suspend | Yes | Middleware Only | No | No | No | MISSING |
| **Characters** | Create | Yes | Yes (API) | No | No | Yes | OK |
| **Characters** | Delete | Yes | Yes (API) | No | No | Yes | OK |
| **Jobs** | Create | Yes | Yes (API) | No | No | Yes | OK |
| **Jobs** | Cancel | Yes | Yes (API) | No | No | Yes | OK |
| **Uploads** | Image | Yes | Yes (API) | No | No | Yes | OK |
| **Secrets** | Create | Yes | Yes (API) | No | No | Yes | OK |
| **Secrets** | Delete | Yes | Middleware Only | No | No | No | MISSING |
| **System** | View Logs | Yes | No | No | No | No | MISSING |

*Finding: Critical admin and security actions like user approval/suspension and viewing system logs are not traced to an actor (user_id) in the backend logs, and are only caught by the blanket request middleware which lacks business context.*
