# Missing Comments and Docstrings

A project-wide audit of 505 backend functions revealed that **62%** are missing docstrings. The following critical files are the most under-documented:

## 1. Backend Service Layer (CRITICAL)
- `backend/app/services/user_service.py`: 90% missing docstrings. Crucial for understanding state transition rules.
- `backend/app/services/job_service.py`: `create_job`, `get_job`, `set_job_status` lack docstrings.
- `backend/app/services/character_service.py`: Most lifecycle management functions are undocumented.

## 2. API Layer (HIGH)
- `backend/app/api/jobs.py`: Complex filtering logic in `list_jobs` is undocumented.
- `backend/app/api/providers.py`: Relationship between provider registry and API response is unclear from code alone.

## 3. Frontend Components (MEDIUM)
- `frontend/components/KeysPanel.tsx`: Logic for environment variable injection is undocumented.
- `frontend/lib/api.ts`: Helper functions like `handleUnauthorized` lack comments on side effects.

## 4. Agents (MEDIUM)
- `agents/scene_composer/handler.py`: Complex logic for orchestration missing flow description.
- `agents/editor/handler.py`: Missing explanation of input artifact requirements.
