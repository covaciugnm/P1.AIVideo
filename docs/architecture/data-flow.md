# Data Flow

Per-stage inputs, outputs, and persistence rules.

## Artifacts pass by reference, never as payloads

Queue messages between agents are small JSON envelopes. They carry **references** to media that lives in object storage — never the media itself.

- **Object storage (MinIO/S3):** all images, audio, intermediate videos, and final renders. Each artifact is addressed by an `s3://` URI under `aivideo-jobs/{job_uuid}/...`.
- **Postgres:** job metadata, `stage_runs`, `qc_findings`, `audit_log`, `policy_decisions`. Rows store URIs + hashes + IDs, not blobs.
- **Redis Streams:** queue topics carrying stage messages. A stage message contains:
  - `job_id`, `stage_id`, `attempt`
  - Input artifact URIs (with sha256 where known)
  - Stage parameters (small JSON: seeds, backend names, fps, etc.)
  - `compliance_token` reference (the JWT string is itself small)
  - Status / error fields on response
- **What is never in a queue message:** raw image bytes, audio bytes, video bytes, model weights, or anything > ~64 KB. If it doesn't fit comfortably in a message envelope, it lives in MinIO and the message carries the URI.

This separation keeps the queue cheap to inspect, makes retries idempotent (the worker re-reads from MinIO, not from the message), and lets stages be restarted independently.

## Job lifecycle

```
1. POST /jobs (brief)                   → Job(state=pending_policy)
2. Compliance Officer policy gate       → Job(state=accepted | rejected)
3. Orchestrator schedules DAG           → Job(state=running)
4. Each agent runs, writes artifacts    → stage_runs rows accumulate
5. QC passes                            → Job(state=qc_passed)
6. Publisher signs + labels             → Job(state=published)
```

Failure paths: any agent failure with `retryable=true` triggers retry up to `max_retries`; non-retryable → `Job(state=failed)` with a structured `failure_reason`.

## Artifact layout in MinIO

```
s3://aivideo-jobs/{job_uuid}/
  brief.json
  policy_decision.json
  compliance_token.jwt            # short-lived, signed; consumed by downstream stages
  script.json
  narration.wav
  phonemes.json
  portrait.png
  portrait_meta.json              # seed, model, hash, identity-guard score
  talking_head.mp4
  broll/{n}.mp4
  music.wav
  reel_draft.mp4
  qc_report.json
  reel_final.mp4                  # signed
  sidecar.json                    # C2PA manifest hash, perceptual hash, model versions
```

## Postgres schema (sketch)

| Table | Purpose |
|---|---|
| `users` | accounts, roles |
| `jobs` | one row per Job; current state + brief |
| `stage_runs` | one row per (job, stage, attempt); inputs/outputs as MinIO URIs, model + seed + hash |
| `qc_findings` | structured QC results, one row per check |
| `audit_log` | append-only; every model call, every policy decision, every operator action |
| `policy_decisions` | what was allowed/blocked and why |
| `model_registry` | known models + hashes + licenses (mirrors `models/MODEL_CARDS.md`) |

## Stage I/O contracts

Each agent owns a Pydantic schema for its inputs/outputs. Schemas are versioned (`schema_version`) and CI fails on incompatible drift.

| Stage | Input | Output |
|---|---|---|
| Scriptwriter | brief + persona + policy hints | `script.json` (scenes, SSML, est_duration) |
| Voice | script SSML, voice profile | `narration.wav`, `phonemes.json` |
| Face | persona spec, seed | `portrait.png`, `portrait_meta.json` |
| LipSync | portrait, narration, phonemes, compliance_token | `talking_head.mp4`, sync_score |
| Editor | talking_head, script, b-roll, music | `reel_draft.mp4` |
| QC | reel_draft + upstream artifacts | `qc_report.json` (pass/fail + findings) |
| Publisher | reel_draft (QC=pass) | `reel_final.mp4`, `sidecar.json` |

## Retention

- Job artifacts auto-purge after `JOB_ARTIFACT_TTL_DAYS` (default 30).
- `audit_log` retained `AUDIT_LOG_RETENTION_DAYS` (default 365).
- A delete endpoint (`DELETE /jobs/{uuid}`) purges artifacts immediately and tombstones `audit_log` rows (the row stays for compliance, but referenced artifacts are hard-deleted).
