# Right Sidebar Log Panel Verification

## 1. Frontend Log Panel (`LogsPanel.tsx`)
- **Source:** `LogsContext` subscribing to `logBus`.
- **Status:** **OK**
- **Verified:**
    - Clearly labeled with source (frontend, api, system).
    - Timestamped.
    - Level visual distinction (colors).
    - Metadata expansion.
    - Filtering by level.
    - Export to JSON/TXT works.

## 2. Backend Log Panel (`BackendLogsPanel.tsx`)
- **Source:** `GET /api/v1/system/logs/backend` polling.
- **Status:** **OK**
- **Verified:**
    - Displays sequence numbers, timestamps, levels, loggers.
    - Polling works (every 2s).
    - Filtering works.
    - Visual indicators for connection status (✓ OK).
    - **CRITICAL GAP:** Does NOT display `security.audit` logs because `log_buffer.py` only listens to `app.*` loggers.

## 3. Separation of Concerns
- Frontend and Backend logs are in separate tabs.
- This is good for clarity but prevents side-by-side correlation of a single action across the stack.

## 4. Leakage Check
- API responses are logged in the frontend log panel.
- Redaction of sensitive fields in response JSON must be verified in the backend.
- `security_audit_service.py` has redaction logic, but standard `app.*` loggers might leak payload if logging full request objects.
