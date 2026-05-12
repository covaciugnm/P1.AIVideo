# Compliance Policy

This document is the authoritative policy for P1.AIVideo. It is referenced by the Compliance Officer agent, by CI policy tests, and by the publishing pipeline.

## Scope

P1.AIVideo generates short reels featuring a **fully synthetic** white Caucasian human performing scripted, lip-synced narration. It is a single-persona system; this is a deliberate scope limit (see also `models/MODEL_CARDS.md`).

## Mandatory rules (cannot be disabled without an explicit compliance review)

1. **No real-person likeness.** The Face agent only outputs synthetic portraits. A celebrity-NN guard rejects outputs that resemble a real public figure above `IDENTITY_GUARD_THRESHOLD`.
2. **No real-voice cloning.** The Voice agent only synthesizes from packaged synthetic voice profiles. Reference-audio input paths are stripped at build time.
3. **No BYO likeness in v1.** Users cannot upload a photo or voice sample. `ALLOW_BYO_LIKENESS=false`. A future consent module would be required to ever enable this.
4. **Visible disclosure.** Every published reel carries a burned-in "AI-generated" overlay (default bottom-left, minimum 4% of frame height).
5. **Metadata disclosure.** Every published reel carries:
   - a C2PA manifest declaring AI generation, model versions, and producer identity;
   - XMP/EXIF `XMP-dc:Source="AI-generated"`.
6. **Audit trail.** Every model call, every policy decision, and every operator action is recorded in `audit_log` (append-only).
7. **Prohibited topics.** See [`prohibited-use.md`](prohibited-use.md). The Compliance Officer rejects briefs that fall into these categories; outputs are re-scanned at QC.

## Jurisdictional context (informational — not legal advice)

- **EU AI Act:** systems generating synthetic image/audio/video must clearly disclose AI generation. Our visible overlay + C2PA + XMP combination is designed to satisfy this.
- **US state-level deepfake laws:** several states (CA, TX, NY, others) restrict synthetic media around elections and intimate imagery. P1.AIVideo prohibits political/electoral content and intimate imagery as a categorical rule (see prohibited-use).
- **Election periods:** even though political content is prohibited at all times, the Compliance Officer applies stricter thresholds during user-configurable election windows.
- **Right-to-deletion:** `DELETE /jobs/{uuid}` purges artifacts immediately. The corresponding `audit_log` rows are tombstoned but retained for compliance.

## How enforcement is wired (gates vs. observation)

P1.AIVideo enforces policy in two distinct ways. The distinction is important to avoid confusion about where compliance "happens":

1. **Explicit DAG gates (control).** The pipeline includes named compliance stages that the orchestrator dispatches like any other stage. A gate has the authority to accept, reject, or loop back. There are four such gates:
   - `policy_gate` (intake)
   - `identity_guard` (post-Face)
   - `pre_lipsync_auth` (issues the `compliance_token` consumed by LipSync)
   - `export_disclosure_validation` (pre-Publisher attestation)
2. **Cross-cutting audit events (observation only).** Every agent emits a structured audit event on each invocation (`audit.compliance` stream). These are persisted to `audit_log` and feed dashboards and after-the-fact review. They do **not** retroactively gate work that has already passed an explicit DAG node.

This means: there is no hidden compliance middleware that can silently reach into a stage and rewrite or block it. Compliance has named seats at the table. If a check is needed somewhere new, a new explicit DAG node is added — not a piece of invisible glue.

The `compliance_token` is minted at `pre_lipsync_auth` and nowhere else. LipSync verifies it before any GPU work and rejects any request that lacks one. Publisher refuses to emit if `export_disclosure_validation` did not pass.

## Operator obligations

Operators of a P1.AIVideo deployment must:

- Publish a Terms of Service and Acceptable Use Policy aligned with [`prohibited-use.md`](prohibited-use.md).
- Keep an internal log of every overridden policy decision (e.g., a human reviewer pushing a borderline output through).
- Refresh the celebrity-figures embedding index quarterly.
- Review `models/MODEL_CARDS.md` whenever a model is added or upgraded.

## Change control

Any change to this document requires:

1. A PR description that names the rule changed and the rationale.
2. Review by a compliance owner (designated per deployment).
3. Update of the corresponding test in `tests/integration/policy/`.
