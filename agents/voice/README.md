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
providers/piper/provider.py     Phase 3B (narrow): real TTS via lazy-imported piper
```

**Phase 3A** introduced the Piper stub: it declares the configured voice's `.onnx` + `.onnx.json`, resolves `PIPER_MODELS_ROOT` (or falls back to `TTS_MODELS_ROOT/piper`), runs an on-disk healthcheck, and raised `ProviderNotImplementedError` from `synthesize()` after asset validation.

**Phase 3B (narrow)** activates the real Piper path. `synthesize()` now:

1. checks assets (unchanged from 3A);
2. lazy-imports `piper.voice.PiperVoice` (falling back to `piper.PiperVoice`) — if the `piper` package isn't installed, raises a clear `ProviderNotImplementedError` and never touches a Piper API;
3. loads the voice and writes a WAV via the stdlib `wave` module to `VoiceRequest.output_path` (or a tempfile).

The `piper` package is **NOT** a hard dependency. Install it manually (`pip install piper-tts`) and place voice files under `$PIPER_MODELS_ROOT` to enable. The test suite passes whether or not `piper` is installed.

No torch / torchvision / torchaudio / onnxruntime imports leak in — verified by a subprocess-isolated test in `tests/integration/test_phase3b_piper.py`. The Phase 2 DAG handler in `agents/voice/handler.py` is still a no-op; wiring it to call `PiperProvider.synthesize()` is deferred.
