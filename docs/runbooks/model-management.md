# Model Management Runbook

How to acquire, verify, mount, and rotate the model weights used by P1.AIVideo.

## Principles

- **No silent downloads.** No agent fetches weights at container build or first run. If weights are missing, the agent fails fast with an actionable error.
- **Pinned by hash.** Every required weight has a recorded SHA256 in `models/MODEL_CARDS.md` and in each provider's `required_assets()`.
- **License-tracked.** Every model has an entry in `models/MODEL_CARDS.md` recording source, license, and commercial-use posture.
- **Bind-mounted, not baked.** Weights live on the host under `./models/` and are bind-mounted into containers read-only in production.

## Directory layout (host)

```
models/
├── MODEL_CARDS.md
├── llm/                              # vLLM-served LLM weights
├── tts/                              # Piper / XTTS-v2 voices
├── image/
│   ├── sdxl/
│   └── loras/
├── lipsync/
│   ├── sadtalker/
│   │   ├── checkpoints/
│   │   └── gfpgan/
│   ├── musetalk/                     # placeholder (v2)
│   └── wav2lip/                      # placeholder (fallback)
├── whisper/
└── identity_guard/
    └── public_figures.index
```

## Mounting into containers

Each GPU agent mounts `./models` → `/models` and reads paths from env. Example (excerpt from `docker/compose.dev.yml` — to be implemented):

```yaml
agent-lipsync:
  volumes:
    - ./models:/models:ro            # read-only in prod; rw in dev only for downloads
  environment:
    LIPSYNC_BACKEND: ${LIPSYNC_BACKEND}
    LIPSYNC_MODELS_ROOT: /models/lipsync
    SADTALKER_CHECKPOINTS_DIR: /models/lipsync/sadtalker/checkpoints
    SADTALKER_GFPGAN_DIR: /models/lipsync/sadtalker/gfpgan
```

For dev convenience you may mount `rw` so download scripts (run *inside* a one-off container) can populate the dir. In production, mount `ro` and run downloads on the host.

## How to download weights (host-side)

Per-provider helper scripts live under `scripts/models/`. They:

1. Print the license summary and require explicit `--accept-license` to proceed.
2. Fetch each asset over HTTPS.
3. Verify SHA256 against the entry in `MODEL_CARDS.md`.
4. Place files at the documented paths.

Example (script not yet implemented; this documents the planned UX):

```bash
./scripts/models/download_sadtalker.sh --accept-license
```

Equivalent fully-manual flow:

1. Read `models/MODEL_CARDS.md` → `sadtalker` section → list of files + URLs + sha256.
2. Download each file with `curl -L -o <dest> <url>`.
3. Verify with `sha256sum -c` against the expected hash.

## How an agent reacts to missing weights

On startup, the LipSync agent:

1. Resolves the provider via the registry (`LIPSYNC_BACKEND`).
2. Calls `provider.required_assets()`.
3. Verifies each asset's presence and sha256.
4. On any missing/mismatched asset, logs a structured error:

```
[lipsync] startup failed: missing or invalid model assets for backend=sadtalker
  missing:
    - /models/lipsync/sadtalker/checkpoints/mapping_00229-model.pth.tar
    - /models/lipsync/sadtalker/gfpgan/GFPGANv1.4.pth
  remediation:
    run `./scripts/models/download_sadtalker.sh --accept-license` on the host,
    then restart this service.
```

5. Exits with code `78` (config error). The container won't restart loop unless `ALLOW_MODEL_AUTODOWNLOAD=true`.

## Override: `ALLOW_MODEL_AUTODOWNLOAD=true`

Setting this to `true` permits the agent to download missing assets at startup, **still subject to sha256 verification**. Intended for ephemeral dev runs only; production deployments should leave it `false`.

## Rotation & upgrades

- New model version → add a new entry in `MODEL_CARDS.md` (don't edit the old one).
- Provider code references a specific asset filename; updating to a new version means updating `required_assets()` in the provider and shipping a migration note.
- The Compliance Officer caches an allowlist of model hashes; an unrecognized hash triggers a `policy_block` unless the operator has approved the new entry.
