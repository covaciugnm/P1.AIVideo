# Wav2Lip Provider (placeholder — rapid-fallback roadmap)

Fast, low-VRAM lip-sync, paired with GFPGAN restoration. **Not implemented in v1.**

Intended use:

- Hosts without enough VRAM for SadTalker/MuseTalk.
- Latency-critical jobs where artifact tolerance is higher.
- A/B comparisons in QA.

When implemented (post-v1):

- Add `provider.py` implementing the `LipSyncProvider` ABC.
- Declare `required_assets()` (Wav2Lip checkpoint + GFPGAN restorer + face detector).
- Add a download script `scripts/models/download_wav2lip.sh`.
- Add an entry in `models/MODEL_CARDS.md` (note: original Wav2Lip weights have restrictive non-commercial terms — license posture must be reviewed before commercial use).
- Add integration tests under `tests/integration/lipsync/wav2lip/`.

Until then, the placeholder provider class (to be added in the implementation phase) will raise `NotImplementedError("wav2lip: planned for fallback tier — see docs/architecture/lipsync-adapter.md")` if selected.

## Expected characteristics

- VRAM: ~4 GB.
- Fastest of the three; most visible mouth artifacts; GFPGAN restoration helps but doesn't eliminate them.
