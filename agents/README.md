# Agents

One subfolder per specialist agent. Each agent is a queue worker (Redis Streams subscriber) that consumes stage messages, runs its logic, and writes artifacts to MinIO + a `stage_runs` row to Postgres.

| Folder | Agent | Purpose |
|---|---|---|
| `orchestrator/` | Orchestrator | Runs the per-job DAG; retries; budget. |
| `scriptwriter/` | Scriptwriter | LLM-driven script generation. |
| `voice/` | Voice | Synthetic-voice TTS + phoneme timestamps. |
| `face/` | Face | Synthetic Caucasian portrait gen + identity guard. |
| `lipsync/` | LipSync | Adapter pattern; SadTalker default. |
| `editor/` | Editor | Compositing, subs, music, disclosure overlay. |
| `qc/` | QC | Pass/fail validation. |
| `publisher/` | Publisher | C2PA sign + XMP label + persist. |
| `compliance_officer/` | Compliance Officer | Policy enforcement at explicit DAG nodes + audit-event consumer. |

Canonical responsibility sheets: [`docs/architecture/agents.md`](../docs/architecture/agents.md).
