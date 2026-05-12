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

## Provider contract (Phase 3A+)

```
core/provider.py                VoiceProvider ABC + VoiceRequest/Result
core/registry.py                resolve(name) → provider instance
providers/piper/provider.py     Phase 3A stub (real Piper inference: Phase 3B)
```

The Phase 3A Piper stub declares the configured voice's `.onnx` + `.onnx.json`, resolves `PIPER_MODELS_ROOT` (or falls back to `TTS_MODELS_ROOT/piper`), runs an on-disk healthcheck, and raises `ProviderNotImplementedError` from `synthesize()` after asset validation. Real Piper inference lands in Phase 3B.
