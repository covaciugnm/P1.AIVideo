# Compliance Officer Agent

Policy enforcement at **explicit DAG nodes**, plus passive audit-event collection from every other stage. The Compliance Officer is not a hidden middleware — it has named seats in the DAG and can only act at those seats.

**Status:** to be implemented in Phase 2 (intake gate + pre-lipsync auth) → Phase 5 (full pipeline coverage incl. export validation).

## Explicit DAG nodes (control)

| Node | Position | Action |
|---|---|---|
| `policy_gate` | First stage of every pipeline. | Validate brief; require `synthetic_person=true`; run banned-topic classifier. Accept or reject. |
| `identity_guard` | Immediately after Face. | CLIP-NN against the public-figures index; reject and loop back to Face on match. |
| `pre_lipsync_auth` | Between `identity_guard` and LipSync. | Confirm all upstream compliance findings are clean. **Issue the `compliance_token`** (this is the only place it is minted). |
| `export_disclosure_validation` | After QC, before Publisher. | OCR for disclosure overlay; final classifier pass on transcript; sample identity-guard on output frames; gate Publisher. |

## Audit-event stream (observation)

Every other agent emits a structured event on `audit.compliance` for each invocation: model + version + hash, seed, prompt hash, duration, decision, error class. The Compliance Officer consumes this stream **only to persist `audit_log` rows** — it does not retroactively gate stages from here. Gates are the four explicit nodes above.

## Token issuance (one place only)

The `compliance_token` is a short-lived JWT minted **only** at the `pre_lipsync_auth` node. It carries:

- `job_id`
- `synthetic_person=true` assertion
- `issued_by="pre_lipsync_auth"` claim
- `issued_at` / `expires_at` (tight TTL, e.g., 1 hour)
- signature against the deployment's compliance key

LipSync verifies the token before any GPU work. There is no other code path that produces a valid token, and there is no bypass flag.

## Outputs

- `policy_decision` rows in Postgres (audit-grade) for each gate decision.
- `policy_block` events on Redis (consumed by the orchestrator on rejection).
- `compliance_token` (signed JWT) on `pre_lipsync_auth` accept.
- Append-only `audit_log` rows for every observed stage event.

## Hard rules

- Gates can reject, but they cannot silently rewrite another agent's output.
- An operator override is itself an audited action with its own row.
- The `audit.compliance` consumer is read-only; it cannot abort in-flight stages.

## Policy source

- `configs/policies/banned_topics.yaml` (rule list).
- An optional local policy classifier model (configured via `POLICY_CLASSIFIER_BACKEND`).

## Outputs

- `policy_decision` rows in Postgres (audit-grade).
- `policy_block` events on Redis (consumed by the orchestrator to abort affected jobs).
- A signed `compliance_token` (on accept).

## Hard rules

- The Officer can veto any stage at any time.
- All decisions are append-only and signed.
- Override of a decision requires an explicit operator action that is itself audited.
