# configs/voices/

Voice profile manifests. Map a stable id (e.g., `en_US_neutral_male_01`) to a Piper / XTTS file and tone metadata.

## Schema (planned)

```yaml
id: en_US_neutral_male_01
backend: piper
file: en_US-amy-medium.onnx        # under $TTS_VOICES_DIR
language: en-US
tone:
  pitch: medium
  pace: medium
  style: friendly
license: "Per Piper voice license (MIT / per-voice — see voice card)"
```

Each entry must reference a voice whose underlying license permits synthetic commercial use in the operator's deployment context. The Voice agent refuses to load a profile that fails license validation.
