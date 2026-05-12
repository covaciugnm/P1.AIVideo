# Editor Agent

Composites the final reel: vertical 1080×1920, subtitles, B-roll, music bed, **AI-disclosure overlay**, end card.

**Status:** to be implemented in Phase 3.

## Tools

- `ffmpeg` filtergraphs for compositing.
- `MoviePy` for higher-level scene assembly.
- `WhisperX` for subtitle alignment.

## Inputs

- `talking_head.mp4` from LipSync.
- `script.json` (for subtitle text + scene cuts).
- B-roll from `assets/broll/`.
- Music from `assets/music/`.
- Disclosure overlay from `assets/disclosure_overlays/`.

## Outputs

- `reel_draft.mp4` (1080×1920, H.264, AAC, 30 fps).

## KPIs

- Aspect ratio exactly 1080×1920.
- Subtitle accuracy ≥ 95% (vs. script).
- Music ducking applied during speech.
- Disclosure overlay legible (OCR-verified at QC).

## Hard rules

- Disclosure overlay is non-optional. `DISCLOSURE_OVERLAY_ENABLED=false` is a build-time error in production builds.
- Overlay is rendered before any branding overlays so branding never covers disclosure.
- Subtitles match the actual TTS output (re-transcribed), not just the script — this catches drift between script and narration.
