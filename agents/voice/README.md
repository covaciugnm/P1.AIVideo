# Voice Agent

Synthesizes narration from the script using a **synthetic** voice profile. **No real-voice cloning.**

**Status:** to be implemented in Phase 1 (Piper) → Phase 3 (XTTS-v2 optional).

## Backend

- Default: Piper (CPU-friendly, fast).
- Optional: Coqui XTTS-v2 (higher quality, GPU). **Reference-audio input paths are stripped at build time** — only packaged synthetic voice profiles are usable.

## Inputs

- `script.json` SSML strings per scene.
- `voice_profile` id (resolved against `configs/voices/`).

## Outputs

- `narration.wav` (48 kHz mono).
- `phonemes.json` — phoneme/viseme timestamps for the LipSync agent.

## KPIs

- WER < 5% when re-transcribed with Whisper.
- LUFS in [-18, -14], true-peak ≤ -1 dBTP.

## Hard rules

- `ALLOW_VOICE_CLONING` must remain `false`.
- The API does not expose a "clone from reference" endpoint.
