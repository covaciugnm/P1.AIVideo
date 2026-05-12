# common/

Shared enums + Pydantic schemas + exception classes used by both `backend/app` and `agents/`.

## Layering rule

```
common  ←  backend/app
common  ←  agents/
```

`common` must never import from `app` or `agents`. Anything in `common` must be safe to import from either side.

## What lives here

- `enums.py` — `JobStatus`, `ComplianceDecisionType`, `StageStatus`, `StageName`. These are the canonical definitions; `backend/app/models/*` re-exports them so existing `from app.models.compliance import ComplianceDecisionType` imports continue to work.
- `schemas.py` — `ArtifactRef`, `StageOutput`, `ComplianceTokenClaims`, `DagState`. Metadata-only envelopes that cross stage boundaries.
- `exceptions.py` — `StageError`, `StageRejection`, `ComplianceTokenError`.

## What does **not** live here

- SQLAlchemy models — still in `backend/app/models/`. The orchestrator imports them from there during Phase 2 (documented coupling; Phase 3+ may move them into a small `common.db` package).
- HTTP clients, queue clients, business logic.
