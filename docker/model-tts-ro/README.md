# F5TTS-Ro wrapper

Optional, opt-in Docker service that fronts upstream F5-TTS configured for
Romanian. The default image installs only `fastapi` + `uvicorn`; torch +
f5-tts are imported lazily — so the container always boots and `/health`
honestly reports whether real inference is reachable.

## Endpoints

| Method | Path | Behavior |
|---|---|---|
| GET | `/health` | Returns 200 with `{status: ready|runtime_missing|assets_missing, details: {...}}`. Never lies about readiness. |
| POST | `/tts/generate` | Generates a Romanian WAV via F5-TTS + the racai-ro adapter. Returns one of `status=generated\|runtime_missing\|assets_missing\|config_missing\|generation_failed`. |

## Safety contract

- **No auto-download.** The container refuses to fetch model weights unless
  `F5TTS_RO_ALLOW_AUTO_DOWNLOAD=true` and the model directory is writable.
- **No fake audio.** Missing torch / f5-tts / model weights / reference voice
  → categorised error response. The wrapper never writes a placeholder WAV.
- **CPU by default.** Override `F5TTS_RO_DEVICE=cuda` and rebuild this
  image on a CUDA-capable host for real-time inference.

## Configuration

| Env | Default | Purpose |
|---|---|---|
| `F5TTS_RO_HOST` | `0.0.0.0` | uvicorn bind host |
| `F5TTS_RO_PORT` | `8080` | uvicorn bind port (mapped to host `8061` by default compose) |
| `F5TTS_RO_MODELS_ROOT` | `/models/f5tts-ro` | Where F5-TTS + racai-ro adapter weights live (mounted from `./models/tts/f5tts-ro`) |
| `F5TTS_RO_REFERENCE_AUDIO` | `${F5TTS_RO_MODELS_ROOT}/reference/voice.wav` | Voice-clone reference WAV |
| `F5TTS_RO_REFERENCE_TEXT` | `Aceasta este o voce de referinta.` | Transcript of the reference WAV |
| `F5TTS_RO_DEVICE` | `cpu` | `cpu` or `cuda` |
| `F5TTS_RO_ALLOW_AUTO_DOWNLOAD` | `false` | Opt-in flag for weight downloads (none performed in the default image) |

## How to actually run real Romanian TTS

The default image is intentionally minimal and CANNOT generate audio yet —
torch and f5-tts are not installed. To enable real inference, rebuild this
image with the heavy ML layer (operator-decided), and supply the racai-ro
adapter weights. See `docs/runbooks/f5tts-ro-runtime.md` for the full
checklist.
