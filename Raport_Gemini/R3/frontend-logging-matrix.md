# Frontend Logging Matrix

| Component / Function | User Action | API Call | Success UI State | Failure UI State | Console Log | Sensitive Exposure? | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `request` (api.ts) | Any | fetch | Silent | Toast | `logBus.emit` | No | OK |
| `CharacterForm` | Create Char | `POST /characters` | Redirect | Toast | None | No | PARTIAL |
| `CreateJobForm` | Create Job | `POST /jobs` | Redirect | Toast | None | No | PARTIAL |
| `LoginForm` | Login | `POST /auth/login` | Redirect | Message | None | No | PARTIAL |
| `KeysPanel` | Upsert Key | `POST /secrets` | Refresh | Toast | None | No | PARTIAL |
| `UserRow` | Approve User | `POST /users/.../approve` | Refresh | Toast | None | No | PARTIAL |

*Note: The frontend relies on a central `request` wrapper in `lib/api.ts` that emits error logs to a browser-internal `logBus`. Success logs are mostly missing from the browser bus, making successful user action flows harder to trace in the sidebar.*
