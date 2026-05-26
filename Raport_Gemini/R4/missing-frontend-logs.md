# Missing Frontend Logs (logBus)

The following UI components or functions are not reporting their state/actions to the `logBus`, making them invisible in the "Logs" sidebar:

## 1. Authentication (CRITICAL)
- `frontend/app/login/page.tsx`: Successful login and failed login are not reported to `logBus`.
- `frontend/app/register/page.tsx`: Registration submission and server response are not reported.

## 2. Character Management (HIGH)
- `frontend/components/CharacterForm.tsx`: Creating or editing a character is silent in `logBus`.
- `frontend/app/characters/[id]/page.tsx`: Deleting a character is silent.

## 3. Configuration (MEDIUM)
- `frontend/components/KeysPanel.tsx`: Upserting or testing an API key is not reported to `logBus`.
- `frontend/components/SettingsPanel.tsx`: Changing UI language or API base URL is not reported.

## 4. Navigation (LOW)
- General navigation breadcrumbs (e.g. "User opened character library") are missing.
