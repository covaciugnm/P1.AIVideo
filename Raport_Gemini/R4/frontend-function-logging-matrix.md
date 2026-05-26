# Frontend Function Logging Matrix (Components/Libs)

| File | Component/Function | User Action | API Call | logBus Intent? | logBus Success? | logBus Failure? | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `app/login/page.tsx` | `LoginPage` | Submit Login | `login()` | NO | NO | NO | MISSING_LOGS |
| `app/register/page.tsx` | `RegisterPage` | Submit Register | `register()` | NO | NO | NO | MISSING_LOGS |
| `components/CreateJobForm.tsx` | `CreateJobForm` | Create Job | `createJob()` | YES | YES | YES | OK |
| `components/CharacterForm.tsx` | `CharacterForm` | Create Character | `createCharacter()` | NO | NO | NO | MISSING_LOGS |
| `components/KeysPanel.tsx` | `KeysPanel` | Upsert Key | `upsertSecret()` | NO | NO | NO | MISSING_LOGS |
| `lib/api.ts` | `request` | ANY | fetch | NO | YES | YES | OK |
| `lib/characters.ts` | `generateImage` | ANY | generate | YES | YES | YES | OK |

*Note: The frontend is very inconsistent. Advanced features like image generation and job creation are perfectly logged, but basic features like login, registration, and character CRUD are silent in the logBus (though the API wrapper catch-all still logs the network event).*
