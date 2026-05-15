# GPU Runtime — Phase 7A Planning & Smoke

This runbook is the **planning** counterpart to
[`gpu-docker.md`](gpu-docker.md). Where `gpu-docker.md` describes how to
*install* the NVIDIA driver + Container Toolkit, this document describes
how P1.AIVideo currently *uses* a GPU (or, deliberately, doesn't), how
to verify the host without committing to any real inference, and what
the GPU surface looks like before Phase 7B chooses the first real video
provider.

## 1. Where GPU code is allowed to live

The default light stack is GPU-free **on purpose**. The split:

| Surface | GPU allowed? | Notes |
|---|---|---|
| `backend` image | **No** | No torch / diffusers / xformers in `backend/pyproject.toml`. The runtime invariants are pinned by `tests/integration/test_phase7a_gpu_planning.py`. |
| `agents` base wheel | **No** | Sub-packages like `agents.lipsync.providers.sadtalker` exist for code organisation but their heavy deps are deferred to a GPU-only image. |
| `frontend` | **No** | Browser-only. |
| `docker/agents/Dockerfile.cuda` | **Yes (stub)** | Still a Phase 0 stub — CUDA base + a user + `sleep infinity`. Real `pip install torch` lines belong here when (and only when) Phase 7B+ promotes a specific provider. |
| `docker/compose.gpu.yml` | **Yes (additive)** | Adds `<<: *gpu-one` reservations to `agent-voice`, `agent-face`, `agent-lipsync`, and (under `--profile llm`) `model-llm`. |
| Default `docker/compose.dev.yml` | **No (profile-gated)** | The three CUDA agents sit behind `profiles: ["gpu"]` so they only start under `--profile gpu`. |

If you ever find yourself adding `torch` to `backend/pyproject.toml` or
to `agents/pyproject.toml`'s base `dependencies`, **stop**. The Phase 7A
invariants will fail in CI. Add it to the GPU image's Dockerfile
instead, behind a phase-specific extra (e.g., `agents[sadtalker]`) that
the GPU image installs but the default backend image does not.

## 2. Verify the host is GPU-capable (no model download)

Two safe Make targets. Neither downloads weights, neither builds the
GPU image.

```bash
# 1. Compose merges cleanly.
make docker-gpu-config-check

# 2. nvidia-smi inside a CUDA container.
#    Skips cleanly if the host lacks driver / NVIDIA Container Toolkit.
#    First run pulls nvidia/cuda:12.4.1-runtime-ubuntu22.04 (~3 GB).
make docker-gpu-smoke
```

What "OK" looks like on a real GPU host:

```
>> nvidia-smi on host:
GPU 0: NVIDIA RTX A4000 (UUID: GPU-…)
>> nvidia-smi inside CUDA container …
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 550.xx  Driver Version: 550.xx        CUDA Version: 12.4                     |
+-----------------------------------------------------------------------------------------+
…
```

What "skip" looks like on a CPU-only dev host (still exits 0):

```
>> NVIDIA Container Toolkit not registered in docker. Skip.
   See docs/runbooks/gpu-runtime.md for setup.
```

Or, with toolkit but no driver:

```
>> nvidia-smi not on host; install the NVIDIA driver first. Skip.
```

Both are intentional — the smoke target is for opt-in pre-flight, not a
hard gate on the default test suite.

## 3. Bringing up the GPU overlay (still no real inference)

The GPU overlay only *attaches device reservations* to the three CUDA
agents — Phase 0 stubs that `sleep infinity`. There is no inference,
no model loading, no API exposure beyond the existing agents.

```bash
# Default light (no GPU services): postgres + redis + backend + frontend
# + orchestrator + 5 metadata agents.
make docker-light-up

# Add the three GPU agents under --profile gpu. The overlay declares
# the device reservation; the agents still sleep.
docker compose \
  -f docker/compose.dev.yml \
  -f docker/compose.gpu.yml \
  --profile gpu \
  up -d agent-voice agent-face agent-lipsync

# Confirm the container sees the GPU:
docker compose -f docker/compose.dev.yml -f docker/compose.gpu.yml \
  --profile gpu exec agent-lipsync nvidia-smi
```

If `nvidia-smi` works inside the container, the host + toolkit + overlay
are correctly wired and Phase 7B can build the first real provider on
top without rediscovering driver issues.

## 4. Phase 7A invariants (pinned by tests)

`make phase7a-test` enforces, in order:

1. The video-generator catalog advertises `requires_gpu=True` +
   `requires_model_files=True` for `sadtalker`, `musetalk`, `wav2lip`,
   `liveportrait`; and `False/False` for the two non-GPU stubs.
2. `/api/v1/video/generate` returns `not_implemented` for every GPU
   placeholder and `not_configured` for `liveportrait` (still
   un-promoted). No MP4, no base64, no `data:video` payload.
3. `docker compose -f compose.dev.yml config --services` does **not**
   list the three CUDA agents.
4. `docker compose -f compose.dev.yml -f compose.gpu.yml config
   --services` *still* doesn't list them — the overlay only attaches
   reservations; it must not surface the services without `--profile
   gpu`.
5. With `--profile gpu`, all three CUDA agents do surface.
6. `docker/agents/Dockerfile.cuda` has no active `pip install torch`,
   `huggingface-cli download`, etc.
7. `backend/pyproject.toml` and `agents/pyproject.toml`'s
   `dependencies` / `[project.optional-dependencies]` tables do not
   list torch / diffusers / xformers / transformers / sadtalker / etc.
8. `python -c "import app.main"` and `python -c "import
   app.services.provider_registry"` finish without pulling any of
   those modules into `sys.modules`.

When (8) fails, *something* in the FastAPI startup path is doing
``from foo import torch``. Track it with
``python -c "import sys; import app.main; print({m for m in sys.modules
if m.startswith('torch')})"`` and remove the offending import — it's
almost always a stray `from agents.lipsync.providers.sadtalker import …`.

## 5. What is **not** in scope for Phase 7A

- Building a GPU image. The CUDA stub stays a stub.
- Downloading SadTalker / MuseTalk / Wav2Lip / LivePortrait weights.
- Installing torch into any image used by `make up` / `make
  docker-light-up`.
- Producing any real MP4. `/api/v1/video/generate` remains
  metadata-only.
- Selecting the first real provider — Phase 7B does that. This runbook
  + [`video-providers.md`](video-providers.md) give Phase 7B the data it
  needs.

## 6. Pre-Phase-7B host checklist

Before promoting any provider:

- [ ] `nvidia-smi -L` shows ≥ 1 GPU with ≥ 16 GB VRAM
      (SadTalker-512 / MuseTalk fit in 8 GB; LivePortrait wants more).
- [ ] `make docker-gpu-config-check` prints **OK**.
- [ ] `make docker-gpu-smoke` prints a `nvidia-smi` table from inside
      the CUDA container (not a skip).
- [ ] `make phase7a-test` is green.
- [ ] `make test` (full suite) is green.
- [ ] Model-licence terms reviewed for the chosen provider — see
      `models/MODEL_CARDS.md`.

Only then open the Phase 7B prompt.
