# MuseTalk Provider (placeholder — v2 roadmap)

Future high-quality alternative to SadTalker. **Not implemented in v1.**

When the implementation phase reaches v2:

- Add `provider.py` implementing the `LipSyncProvider` ABC.
- Declare `required_assets()` with exact filenames + sha256 + URLs.
- Add a download script `scripts/models/download_musetalk.sh`.
- Add an entry in `models/MODEL_CARDS.md` with license review notes.
- Add integration tests under `tests/integration/lipsync/musetalk/`.

Until then, the placeholder provider class (to be added in the implementation phase) will raise `NotImplementedError("musetalk: planned for v2 — see docs/architecture/lipsync-adapter.md")` if selected.

## Source (target)

- Repo: <https://github.com/TMElyralab/MuseTalk>
- License: verify at integration time.

## Expected characteristics

- VRAM: ~10 GB.
- Visibly better mouth shape on close-ups vs. SadTalker.
- Slower wall-clock per frame.
