# Failure Recovery — Phase 8D Cancel / Retry

This runbook covers operator-facing controls for cancelling
in-progress jobs and requesting a retry on failed / rejected ones.

> **Phase 8D is metadata-only.** Cancel marks the job as `rejected`
> with a documented operator-cancellation reason and writes a
> `compliance_events` row. It does **not** kill an OS process that
> may already be running a stage handler on a worker. Retry records
> the operator's intent (`retry_count++`, `retry_requested_at`) and
> emits an audit event; actually re-running the DAG when a worker
> picks the job back up is a future-phase concern.

## 1. Endpoints

### Cancel

```bash
POST /api/v1/jobs/{job_id}/cancel
Content-Type: application/json

{ "reason": "optional operator-supplied reason" }
```

Behavior:

| Job status | Result |
|---|---|
| `pending_compliance` / `accepted` | 200 — status flips to `rejected`, `rejection_reason="cancelled by operator: <reason>"`, `recovery_metadata.cancelled_at` + `cancellation_reason` populated, compliance event `gate=job_cancel decision=reject` written. |
| `published` / `rejected` / `failed` | 409 — already terminal; the API refuses to overwrite the state. |
| (unknown id) | 404. |

The endpoint also accepts the request under the legacy `/jobs/{id}/cancel`
mount for clients that haven't migrated to the `/api/v1` prefix.

### Retry

```bash
POST /api/v1/jobs/{job_id}/retry
Content-Type: application/json

{ "stage_name": "lipsync", "reason": "transient GPU OOM" }
```

Both `stage_name` and `reason` are optional.

Behavior:

| Job status | Result |
|---|---|
| `failed` / `rejected` | 200 — `recovery_metadata.retry_count` increments, `retry_requested_at` set (+ `retry_stage_name` / `retry_reason` when provided), compliance event `gate=job_retry decision=accept` written. The job's `status` is **unchanged** — the worker pipeline reads the marker and decides when to actually re-run. |
| `published` | 409 — published is a success terminal; retry doesn't apply. |
| `pending_compliance` / `accepted` | 409 — job is still running / queued. |
| (unknown id) | 404. |

`retry_count` accumulates across calls — operators can request multiple
retries without losing the history.

## 2. Recovery metadata

`jobs.recovery_metadata` is a JSON column (added in Alembic migration
`0002_phase8d_recovery_metadata`). Fields populated by Phase 8D:

| Field | Source | Notes |
|---|---|---|
| `cancelled_at` | `cancel` endpoint | ISO 8601 string. |
| `cancellation_reason` | `cancel` endpoint payload | Defaults to `"cancelled by operator"` when omitted. |
| `retry_requested_at` | `retry` endpoint | ISO 8601 string. |
| `retry_count` | `retry` endpoint | Monotonic counter; starts at 1 on first retry call. |
| `retry_stage_name` | `retry` endpoint payload | Optional. |
| `retry_reason` | `retry` endpoint payload | Optional. |
| `last_error_code` | future worker | Reserved; populated when the worker observes a categorised stage failure (Phase 8E+). |

The column is nullable and starts empty — existing jobs and pre-8D
tests are unaffected.

## 3. Audit trail

Every cancel / retry writes a `compliance_events` row so the existing
audit timeline picks them up alongside policy / identity-guard
decisions:

| `gate` | `decision` | `reasons[]` | `extra` |
|---|---|---|---|
| `job_cancel` | `reject` | `[cancellation_reason]` | `{cancelled_at: ISO}` |
| `job_retry` | `accept` | `[retry_reason or "operator-requested retry"]` | `{retry_requested_at, retry_count, retry_stage_name}` |

The Phase 4A compliance-events list endpoint returns these rows
without code changes.

## 4. Frontend

The Job Detail page renders a new **Recovery controls** card with two
buttons:

- **Cancel job** — enabled while the job is non-terminal. Triggers
  a `window.prompt()` for the optional reason, then POSTs to
  `/api/v1/jobs/{id}/cancel`.
- **Retry job** — enabled when the job is in `failed` or `rejected`
  state. Triggers a `window.confirm()` then POSTs to
  `/api/v1/jobs/{id}/retry`.

Both buttons log to the right-sidebar log bus (`info` on success,
`warning` on API failure). After a successful mutation the page does
a `window.location.reload()` so the new status + recovery metadata
land immediately.

When `recovery_metadata` carries either a `cancelled_at` or a
non-zero `retry_count`, the card also renders a definition list of
the historical operator actions (timestamps, reasons, counters) for
audit visibility.

## 5. Limitations

- **No OS process kill.** Cancel marks the job rejected; if a worker
  is mid-stage on this job, the worker won't notice until it next
  checks the job's status. Building cancellation observation into
  long-running stage handlers (e.g., SadTalker inference) is a
  Phase 8E+ task.
- **No history truncation.** Retrying does not delete prior
  `stage_runs` or `artifacts`. This is a deliberate audit posture —
  every attempt is preserved.
- **No automatic re-execution.** A retry request flips the marker
  but does not currently re-trigger the orchestrator. Operators have
  to manually re-queue the job (future worker behavior pending).

## 6. Tests

`make phase8d-test` runs 15 invariants:

- 404 / 409 / 200 paths on cancel + retry.
- Default-reason fallback ("cancelled by operator").
- `extra="forbid"` on both request bodies.
- Counter increments across multiple retry calls.
- History preservation (artifacts from prior attempts survive).
- Legacy `/jobs/...` mirror works alongside `/api/v1/jobs/...`.
- `recovery_metadata` round-trips through `GET /jobs/{id}` (JobDetail
  schema).
- `app.api.jobs` module-load isolation invariant unchanged (no torch).

The Phase 6B drift guard remains green — the new migration
(`0002_phase8d_recovery_metadata`) is the canonical capture of the
`recovery_metadata` column.
