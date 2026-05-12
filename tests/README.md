# tests/

Cross-cutting tests. Per-component unit tests live next to each component (e.g., `backend/tests/`, `agents/<name>/tests/`).

## Layout

```
tests/
├── integration/        # multi-service tests against compose.test.yml
│   ├── policy/         # banned-topic precision/recall
│   ├── identity_guard/ # positive + negative tests
│   ├── lipsync/        # per-provider adapter tests (sadtalker, ...)
│   └── disclosure/     # overlay + C2PA + XMP presence on every published output
├── e2e/                # full reel runs (GPU + models required)
└── fixtures/           # briefs, scripts, audio samples, golden outputs
```

## Test tiers

- **Unit** — fast, no Docker.
- **Integration** — `compose.test.yml` with mock model servers; no GPU.
- **GPU smoke** — `compose.gpu.yml` with real models; runs on a self-hosted CI runner with GPU.
- **e2e** — produces an actual reel and validates the full disclosure stack.

## Compliance gates

- The disclosure test suite runs on every PR and gates merges.
- The identity-guard test suite runs on every PR.
- The policy test corpus (~200 briefs) runs nightly with precision/recall thresholds enforced.
