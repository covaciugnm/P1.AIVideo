# Orchestrator Agent

Runs the per-job DAG defined in `pipelines/*.yaml`. Built on LangGraph.

**Status:** to be implemented in Phase 2.

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
