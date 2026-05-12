# Publisher Agent

Finalizes a QC-passed reel: embeds C2PA, writes XMP/EXIF flags, computes hashes, persists.

**Status:** to be implemented in Phase 5.

## Tools

- `c2patool` for the Content Credentials manifest.
- `exiftool` for XMP fields.
- `ffmpeg` for any final container fixup.

## Inputs

- `reel_draft.mp4` (QC = pass).
- All upstream `stage_runs` rows (for model-version provenance).

## Outputs

- `reel_final.mp4` (signed).
- `sidecar.json`:
  ```json
  {
    "perceptual_hash": "...",
    "sha256": "...",
    "c2pa_manifest_hash": "...",
    "models_used": [
      { "stage": "scriptwriter", "model": "...", "sha256": "..." },
      { "stage": "voice",        "model": "...", "sha256": "..." }
    ],
    "produced_at": "2026-05-12T18:00:00Z"
  }
  ```

## Hard rules

- Refuses to emit if any of (visible overlay, C2PA manifest, XMP flag) is missing.
- Refuses to emit if QC result is anything other than `pass`.
- Writes a `disclosure_failure` audit row on refusal.

See [`docs/compliance/disclosure.md`](../../docs/compliance/disclosure.md).
