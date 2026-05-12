# Orchestrator Agent

Runs the per-job DAG defined in `pipelines/*.yaml`. **Phase 2 ships a hand-rolled state machine** in `dag.py`; LangGraph adoption is deferred until the DAG gains branching/retry/parallel work that justifies the dep.

**Status:** Phase 2 — no-op DAG runner is implemented. Phase 3+ will replace each stage's no-op handler with the real implementation; the orchestrator interface stays stable.

## Coupling notes (Phase 2 limitations — tracked for Phase 3 cleanup)

### Orchestrator → backend DB

`agents/orchestrator/dag.py` and `agents/orchestrator/handlers.py` import from `backend/app/*` for DB access (`app.services.job_service`, `app.services.stage_run_service`, `app.models.*`). This is a one-directional coupling — the backend never imports from `agents/`.

The shared *types* (enums, Pydantic schemas, exceptions) were moved to `common/` so the orchestrator no longer depends on backend for type definitions. The remaining DB-access coupling is tracked as a Phase 3 refactor candidate: when/if the orchestrator runs in its own container with its own DB session pool, a small `common.db` package can host the SQLAlchemy declarations.

### `agents/` packaging

`pip install -e ./agents` currently exposes the agent submodules as top-level packages (`compliance_officer`, `orchestrator`, …) rather than under an `agents.` namespace, because the flat directory layout doesn't fit setuptools' standard package layouts cleanly without restructuring. As a result, the project depends on `tests/conftest.py` adding the repository root to `sys.path` so that `import agents.compliance_officer` works in tests.

This will be addressed in Phase 3 by restructuring the `agents/` directory into a proper Python package (likely `agents/agents/...` flat layout or a `src/` layout). Until then, `common/` is the only shared package that is properly installable, and the `sys.path` entry for `agents.*` is documented in `tests/conftest.py`.

## Responsibilities

- Subscribe to `job.created` events from Redis.
- Load the pipeline definition (default `pipelines/reel_default.yaml`).
- Dispatch stage messages to specialist agents in DAG order.
- Track per-stage state, retries, and budget (max wall time, max GPU minutes).
- Aggregate `stage_runs` into a final `Job` state transition.

## Hard rules

- Never invoke a downstream stage without a valid upstream `compliance_token`.
- Never bypass the Compliance Officer's veto.
- Never import a concrete model provider — always dispatch by name.

## Inputs / outputs

- **Input:** `JobCreated` event (job_id, brief, pipeline name).
- **Output:** stage messages on `stage.<agent>` streams; `Job.state` transitions.
