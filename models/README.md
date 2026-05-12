# models/

Local model weights live here. **This directory is gitignored** — only the README, `MODEL_CARDS.md`, and `.gitkeep` files are tracked.

See:

- [`MODEL_CARDS.md`](MODEL_CARDS.md) — per-model card with source, license, hashes.
- [`../docs/runbooks/model-management.md`](../docs/runbooks/model-management.md) — how to download, verify, mount, rotate.

## Layout

```
models/
├── llm/                       # vLLM-served LLM weights
├── tts/                       # Piper / XTTS-v2 voices
├── image/
│   ├── sdxl/
│   └── loras/
├── lipsync/
│   ├── sadtalker/             # v1 default
│   ├── musetalk/              # v2 placeholder
│   └── wav2lip/               # fallback placeholder
├── whisper/
└── identity_guard/
    └── public_figures.index
```

## Hard rules

- No silent downloads at build or first run.
- All weights pinned by sha256.
- License posture must be recorded in `MODEL_CARDS.md` before a model is used.
