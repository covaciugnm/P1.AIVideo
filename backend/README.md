# backend/

FastAPI service. Owns: auth, job CRUD, artifact URLs, audit log read API, frontend WebSocket.

**Status:** to be implemented in Phase 1 onward.

## Planned layout

```
backend/
├── app/
│   ├── main.py                # FastAPI app factory
│   ├── api/                   # routers: jobs, auth, artifacts, audit, healthz
│   ├── core/                  # config, logging, deps, security
│   ├── models/                # Pydantic + SQLAlchemy models
│   └── services/              # job service, queue publisher, artifact service
├── tests/
└── pyproject.toml
```

## Responsibilities

- Authenticate users (JWT + refresh).
- Validate briefs against the Pydantic schema.
- Persist `Job` rows; publish `job.created` to Redis Streams.
- Serve presigned MinIO URLs for artifact retrieval.
- Expose a WebSocket for live progress updates.
- Expose audit-log read endpoints (operator-only).

## Not responsibilities

- No model invocation. The backend only enqueues; agents do the work.
- No policy decisions. The Compliance Officer agent owns those.
