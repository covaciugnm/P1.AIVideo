# LipSync Core — Adapter Contract

This directory will host the abstract contract that every lip-sync provider implements. **No code in this scaffold phase** — this README documents the planned shape.

## Planned files

| File | Purpose |
|---|---|
| `provider.py` | `LipSyncProvider` ABC. |
| `types.py` | `LipSyncRequest`, `LipSyncResult`, `AssetSpec`, `ProviderHealth` Pydantic models. |
| `registry.py` | `PROVIDERS` mapping + `resolve(name)` function. |
| `exceptions.py` | `UnsupportedBackendError`, `MissingAssetsError`, `ComplianceTokenError`, ... |

## Planned interface (informational)

```python
class LipSyncProvider(ABC):
    name: ClassVar[str]
    def required_assets(self) -> list[AssetSpec]: ...
    def healthcheck(self) -> ProviderHealth: ...
    def synthesize(self, req: LipSyncRequest) -> LipSyncResult: ...
```

See [`docs/architecture/lipsync-adapter.md`](../../../docs/architecture/lipsync-adapter.md) for the full spec.

## Conventions

- Providers are imported lazily inside `registry.py` so a missing optional provider (e.g., MuseTalk's deps not installed) doesn't crash the agent.
- Providers must never reach the network outside of explicit asset-download flows gated by `ALLOW_MODEL_AUTODOWNLOAD`.
- Providers must verify `compliance_token` before any GPU work.
