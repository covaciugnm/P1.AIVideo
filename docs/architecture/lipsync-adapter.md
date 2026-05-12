# LipSync Adapter

The lip-sync stage uses a **provider/adapter pattern** so the underlying model can be swapped via env without touching orchestration code.

## Goals

- **Default `LIPSYNC_BACKEND=sadtalker`** — SadTalker is fully implemented and ships as v1.
- **MuseTalk** — placeholder provider; planned for v2.
- **Wav2Lip + GFPGAN** — placeholder provider; rapid-fallback for low-VRAM or speed-critical jobs.
- The orchestrator never imports a concrete provider. It enqueues a `LipSyncRequest` carrying the desired backend name; the LipSync agent resolves a provider via a registry.

## Folder layout

```
agents/lipsync/
├── core/
│   ├── provider.py          # LipSyncProvider ABC (the contract)
│   ├── types.py             # LipSyncRequest, LipSyncResult, AssetSpec, ProviderHealth
│   ├── registry.py          # name → provider class, populated from env
│   └── exceptions.py
├── providers/
│   ├── sadtalker/           # default — fully implemented
│   ├── musetalk/            # placeholder — raises NotImplementedError("v2 roadmap")
│   └── wav2lip/             # placeholder — raises NotImplementedError("fallback roadmap")
├── agent.py                 # queue worker; resolves backend via registry
└── Dockerfile               # CUDA base; no weight downloads at build
```

## Provider contract (target shape — to be implemented in Phase 3)

```python
class LipSyncProvider(ABC):
    name: ClassVar[str]                       # "sadtalker" | "musetalk" | "wav2lip"

    @abstractmethod
    def required_assets(self) -> list[AssetSpec]:
        """Files the provider needs under $LIPSYNC_MODELS_ROOT, with sha256 + URL hint."""

    @abstractmethod
    def healthcheck(self) -> ProviderHealth:
        """Verify GPU, weights present, hashes match. Called on agent startup."""

    @abstractmethod
    def synthesize(self, req: LipSyncRequest) -> LipSyncResult:
        """Run lip-sync. Must validate req.compliance_token before any work."""
```

### Request / Result shape

```python
class LipSyncRequest:
    job_id: UUID
    portrait_path: str          # MinIO URI
    audio_path: str             # MinIO URI
    phonemes_path: str          # MinIO URI
    fps: int                    # default 25
    seed: int
    compliance_token: str       # JWT-signed; verified before any compute
    params: dict                # provider-specific knobs (kept narrow & validated)

class LipSyncResult:
    video_path: str             # MinIO URI for the produced talking_head.mp4
    frame_count: int
    sync_score: float           # SyncNet-style confidence in [0, 1]
    model_version: str
    seed_used: int
    duration_ms: int
```

## Registry & resolution

`registry.py` maps backend names to provider classes:

```python
PROVIDERS: dict[str, type[LipSyncProvider]] = {
    "sadtalker": SadTalkerProvider,
    "musetalk":  MuseTalkProvider,     # raises NotImplementedError until v2
    "wav2lip":   Wav2LipProvider,      # raises NotImplementedError until fallback impl
}

def resolve(name: str) -> LipSyncProvider:
    if name not in PROVIDERS:
        raise UnsupportedBackendError(name)
    return PROVIDERS[name]()
```

The agent reads `LIPSYNC_BACKEND` at startup, instantiates the provider once, runs `healthcheck()`, and only then begins consuming the queue.

## Asset management

Each provider declares its required assets:

```python
class SadTalkerProvider:
    def required_assets(self) -> list[AssetSpec]:
        return [
            AssetSpec(
                path="sadtalker/checkpoints/mapping_00229-model.pth.tar",
                sha256="...",
                source="https://github.com/OpenTalker/SadTalker (license: Apache-2.0)",
                size_mb=...,
            ),
            # ... etc.
        ]
```

On startup:

1. Resolve provider via registry.
2. Call `required_assets()`.
3. For each asset, verify presence under `$LIPSYNC_MODELS_ROOT` and verify sha256.
4. If any are missing or mismatched: **fail fast** with a structured error listing each missing file and the helper script (`scripts/models/download_sadtalker.sh`) to run on the host.
5. **Never auto-download** unless `ALLOW_MODEL_AUTODOWNLOAD=true` is set. Even then, only over verified hashes.

## Compliance gating

`synthesize()` must, before any GPU work:

- Verify `compliance_token` signature and expiry.
- Verify the token's `job_id` matches the request.
- Verify the token was issued by the `pre_lipsync_auth` DAG node (carries that claim) and asserts `synthetic_person=true`.
- Reject with `ComplianceTokenError` otherwise — no bypass flag.

The token is minted **only** by the `pre_lipsync_auth` compliance node, which runs after `identity_guard` has cleared the synthetic portrait. There is no other code path that produces a valid token.

## Upgrade path

- **v1:** ship SadTalker as the default and only implemented provider.
- **v2:** implement `MuseTalkProvider`; mark it `experimental` in the pipeline config until validated; flip `LIPSYNC_BACKEND` per-job to opt in.
- **Fallback:** implement `Wav2LipProvider` + GFPGAN restoration for low-VRAM hosts; selectable per-job.

## See also

- [`../runbooks/model-management.md`](../runbooks/model-management.md) — how to mount and verify weights.
- [`../runbooks/gpu-docker.md`](../runbooks/gpu-docker.md) — NVIDIA Container Toolkit setup.
- [`../../agents/lipsync/README.md`](../../agents/lipsync/README.md) — implementation-level README.
