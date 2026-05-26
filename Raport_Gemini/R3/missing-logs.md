# Missing Logs Report

This report lists functions and actions that currently have **zero** or **insufficient** logging.

## Backend - Critical
- `backend/app/services/user_service.py`: All functions (`authenticate`, `register_user`, `approve`, `suspend`, `soft_delete`).
- `backend/app/api/auth.py`: All endpoints (`login`, `register`, `change_password`).
- `backend/app/api/users.py`: All endpoints (`approve_user`, `suspend_user`, etc).
- `backend/app/api/secrets.py`: `list_secrets` and `delete_secret`.
- `backend/app/api/system.py`: `get_backend_logs`.

## Backend - High
- `backend/app/api/characters.py`: `list_characters` (GET is silent).
- `backend/app/api/jobs.py`: `list_jobs` (GET is silent).
- `backend/app/core/security.py`: `_resolve_user` (Fails are silent, don't log the reason for token failure or user lookup failure).

## Frontend
- Major state transitions (Login, Logout, Navigation).
- Successful API responses (mostly silent in `logBus`).
- Validation errors in forms (often only in UI, not in `logBus`).

## Observability Gaps
- `user_id` is missing from almost all log records.
- `request_id` correlation is missing.
- Duration for LLM/TTS provider calls is often missing.
