# Face Agent

Generates a **synthetic** white Caucasian portrait via SDXL + a persona LoRA.

**Status:** to be implemented in Phase 3.

## Backend

- SDXL base + a persona LoRA trained on a licensed synthetic-face dataset.
- LoRA weights pinned in `models/image/loras/` and tracked in `models/MODEL_CARDS.md`.

## Inputs

- Persona spec: age range, attire, lighting, framing.
- Seed (for reproducibility).

## Outputs

- `portrait.png` (1024×1024 or higher, square; cropped per editor needs).
- Optional driving frames (slight turn, neutral expressions) if the LipSync provider wants them.
- `portrait_meta.json`: seed, model + LoRA versions, identity-guard score.

## KPIs

- Face-detect confidence ≥ 0.9.
- NSFW score = 0.
- Identity-guard CLIP-NN score < `IDENTITY_GUARD_THRESHOLD`.

## Hard rules

- Refuses to accept a real-person image as input.
- Negative prompt always includes "real person, celebrity, identifiable likeness".
- On identity-guard match, regenerates with a new seed.
- After N consecutive identity-guard rejections, fails the job with `identity_guard_exhausted`.

See [`docs/compliance/identity-guard.md`](../../docs/compliance/identity-guard.md).
