# Agent Responsibility Sheets

This is the canonical job description for each agent. Per-agent READMEs under `agents/<name>/README.md` mirror this with implementation pointers.

---

## Orchestrator

- **Mission:** turn a `Job` into a successful set of artifacts within budget.
- **Inputs:** validated brief, pipeline YAML (`pipelines/reel_default.yaml`).
- **Outputs:** stage task messages on Redis streams; final `job.state` transitions.
- **KPIs:** end-to-end latency, retry rate, % jobs completed within budget.
- **Authority:** retry, fallback to alternate models (via env or pipeline config), abort.
- **Hard rules:** never invoke an agent without a valid upstream `compliance_token`.

## Scriptwriter

- **Mission:** craft a hook-driven, duration-bounded script in target language/tone.
- **Inputs:** brief, persona, banned-words list.
- **Outputs:** `script.json` (scenes, SSML, est. duration).
- **KPIs:** duration adherence ±5%, readability score in range, banned-content = 0.
- **Hard rules:** the brief is treated as untrusted input — the system prompt is isolated and a per-output policy classifier runs before returning.

## Voice

- **Mission:** produce natural narration from a **synthetic** voice profile.
- **Inputs:** script SSML, voice profile id.
- **Outputs:** `narration.wav` (48 kHz mono), `phonemes.json`.
- **KPIs:** WER on re-transcription < 5%, LUFS in [-18, -14].
- **Hard rules:** voice-cloning input paths (audio reference input) are stripped at build time. The agent's API does not accept reference audio.

## Face

- **Mission:** generate a **synthetic** white Caucasian portrait matching the persona config.
- **Inputs:** persona spec (age range, attire, lighting), seed.
- **Outputs:** `portrait.png` + optional driving frames; `portrait_meta.json` with identity-guard score.
- **KPIs:** face-detect confidence ≥ 0.9, NSFW = 0, identity-guard CLIP-NN below threshold.
- **Hard rules:** the agent refuses to accept a real-person image as input. Negative prompt always includes "real person, celebrity, identifiable likeness". On identity-guard match → reject and request a new seed.

## LipSync

- **Mission:** animate the portrait to speak the narration with phoneme-accurate sync.
- **Inputs:** portrait, narration, phonemes, **valid `compliance_token`**, backend (default `sadtalker`).
- **Outputs:** `talking_head.mp4`, sync_score, frame_count.
- **KPIs:** SyncNet confidence ≥ threshold, no temporal flicker, eye-blink present.
- **Implementation:** adapter pattern — see [`lipsync-adapter.md`](lipsync-adapter.md). The orchestrator never imports a provider directly.
- **Hard rules:** rejects any `LipSyncRequest` without a valid `compliance_token`. No bypass flag exists.

## Editor

- **Mission:** assemble the final reel with subs, B-roll, music, branding, and the AI-disclosure overlay.
- **Inputs:** talking_head, script, asset library, brand template.
- **Outputs:** `reel_draft.mp4`.
- **KPIs:** correct aspect ratio (1080×1920), subtitle accuracy, music ducking compliance.
- **Hard rules:** the disclosure overlay is non-optional and is rendered before any branding overlays. `DISCLOSURE_OVERLAY_ENABLED=false` is a build-time error in production builds.

## QC

- **Mission:** decide pass/fail with a structured report.
- **Inputs:** `reel_draft.mp4` + all upstream artifacts.
- **Outputs:** `qc_report.json`.
- **KPIs:** false-pass rate < 1% on the test set.
- **Authority:** request regeneration of specific upstream stages (with a reason); two consecutive failures escalate to a human review queue.

## Publisher

- **Mission:** finalize, sign, label, and persist the deliverable.
- **Inputs:** QC-passed `reel_draft.mp4`.
- **Outputs:** `reel_final.mp4`, `sidecar.json` (C2PA, hashes, model versions).
- **KPIs:** 100% of outputs carry visible + metadata AI disclosure.
- **Hard rules:** refuses to emit if any of (visible overlay, C2PA manifest, XMP flag) is missing.

## Compliance Officer

The Compliance Officer is **not** a hidden middleware. It is implemented as a worker agent that runs at **explicit DAG nodes**. In addition, every other agent emits structured **compliance audit events** to a dedicated stream, which the Compliance Officer consumes for logging only — *not* to retroactively block work that has already advanced past a gate.

- **Mission:** enforce policy at explicit DAG checkpoints and record an audit trail of every stage.
- **Inputs:** stage artifacts produced upstream of each gate; policy ruleset (`configs/policies/banned_topics.yaml`).
- **Outputs:** `policy_decision` records (audit-grade), `compliance_token` (issued only at the pre-LipSync authorization node), append-only audit-event rows.

### Explicit compliance DAG nodes

| Node | Position in DAG | Purpose |
|---|---|---|
| `policy_gate` | First stage of every pipeline. | Validate brief; require `synthetic_person=true`; run banned-topic classifier; accept or reject the job. |
| `identity_guard` | Immediately after Face. | Run CLIP-NN against the public-figures index; reject portraits that resemble a real person; loop back to Face on failure. |
| `pre_lipsync_auth` | Between `identity_guard` and LipSync. | Confirm all upstream compliance findings are clean; **issue the `compliance_token`** that LipSync requires. This is the only place the token is minted. |
| `export_disclosure_validation` | After QC, before Publisher. | Final compliance attestation: verify the burned-in disclosure overlay is present (OCR), the policy classifier is still clean on the final transcript, and identity-guard sampling on output frames passes. Without this attestation, Publisher refuses to emit. |

### Cross-cutting compliance audit events (observation, not control)

Every other agent (Scriptwriter, Voice, Face, LipSync, Editor, QC, Publisher) emits structured audit events to the `audit.compliance` stream at each invocation: model + version + hash, seed, prompt hash, decision, duration, error class. These are written to the `audit_log` table for traceability. They do **not** vote on whether a stage passes — the gating nodes above do that.

### Authority

- The Compliance Officer can **reject** at any of its DAG nodes; the orchestrator then aborts the job or loops back to the upstream stage per the pipeline definition.
- It has no path to silently rewrite or replace another agent's output.
- An operator can override a borderline decision only through an audited admin action; the override itself is recorded.

### Hard rules

- The `compliance_token` is short-lived (typically 1 hour), signed by the deployment's compliance key, scoped to a single `job_id`, and minted **only** at the `pre_lipsync_auth` node.
- LipSync rejects any request without a valid token. There is no bypass flag.
- Publisher rejects any output without an `export_disclosure_validation` pass.

---

## Cross-cutting expectations

- Every agent emits structured JSON logs and Prometheus metrics with stage labels.
- Every agent must implement: `healthcheck`, `version`, `process(message)` with idempotency keyed on (job_id, stage, attempt).
- Every agent must record `model_id`, `model_sha256`, `seed`, `container_digest`, `prompt_sha256` (where applicable) in its `stage_runs` row.
