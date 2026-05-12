# Architecture Overview

This document describes the runtime topology of P1.AIVideo. For motivation and scope see [`../PROJECT_PLAN.md`](../PROJECT_PLAN.md).

## Layers

1. **Edge / Reverse proxy** — Traefik terminates TLS and routes to the backend + frontend.
2. **UI layer** — Next.js frontend; talks to the backend over REST + WebSocket.
3. **API layer** — FastAPI backend; auth (JWT + RBAC), job CRUD, artifact retrieval.
4. **Data layer** — Postgres (metadata, audit), MinIO (S3-compatible object store for artifacts), Redis (queue + cache).
5. **Orchestration layer** — Orchestrator agent runs a LangGraph DAG per job.
6. **Agent layer** — One worker container per specialist agent: scriptwriter, voice, face, lipsync, editor, qc, publisher, compliance_officer.
7. **Model layer** — Long-running model servers (e.g., `model-llm` running vLLM) plus per-agent in-process model loaders for heavyweight stages.
8. **Observability** — Prometheus scrapes metrics; Grafana dashboards; structured JSON logs shipped to stdout for Docker log drivers.

## Topology

```
                  Internet
                     │
                     ▼
                ┌──────────┐
                │ Traefik  │  TLS, HSTS, routing
                └────┬─────┘
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
   ┌──────────┐             ┌──────────┐
   │ Frontend │             │ Backend  │ FastAPI
   └──────────┘             └────┬─────┘
                                 │
            ┌────────────────────┼────────────────────┐
            ▼                    ▼                    ▼
        ┌─────────┐         ┌──────────┐         ┌──────────┐
        │Postgres │         │  Redis   │         │  MinIO   │
        └─────────┘         └────┬─────┘         └──────────┘
                                 │
                                 ▼
                          ┌───────────────┐
                          │ Orchestrator  │
                          └──────┬────────┘
                                 │ enqueues stage messages
        ┌────────────┬───────────┼───────────┬────────────┬───────────┐
        ▼            ▼           ▼           ▼            ▼           ▼
   scriptwriter   voice       face       lipsync       editor        qc → publisher
                                                                       ▲
                                                                       │
                                                            Compliance Officer
                                                            (cross-cutting; can veto)
```

## Communication

- **Frontend ↔ Backend:** REST for CRUD, WebSocket for live progress.
- **Backend ↔ Orchestrator:** the backend writes a `Job` row and pushes a `job.created` event to Redis Streams. The orchestrator subscribes.
- **Orchestrator ↔ Agents:** each agent subscribes to its dedicated Redis stream (`stage.<agent>`). The orchestrator sends a stage message; the agent ACKs on completion and writes a `stage_runs` row.
- **Agents ↔ Storage:** all artifacts go through MinIO; agents never write to a shared filesystem.
- **Agents ↔ Models:** model servers are reached via internal HTTP (e.g., vLLM OpenAI-compatible API) or in-process model loaders for ones that don't justify a separate server.

## Determinism & reproducibility

Every stage records:

- `model_id` + `model_sha256`
- `prompt_sha256`
- `seed`
- `container_digest`
- `params` (the full JSON config used)

This makes failed runs reproducible and supports the audit trail required by [`../compliance/policy.md`](../compliance/policy.md).

## See also

- [`data-flow.md`](data-flow.md) — per-stage inputs/outputs and persistence.
- [`agents.md`](agents.md) — full agent responsibility sheets.
- [`lipsync-adapter.md`](lipsync-adapter.md) — the LipSync provider interface.
