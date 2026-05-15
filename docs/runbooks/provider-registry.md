# Provider registry (Phase 6D)

The project's tools (LLM, TTS, video generator, audio processor, image
processor) are pluggable provider categories — Piper / Ollama /
SadTalker are first examples, not the architecture. This runbook
explains the registry, the API surface, and how an operator adds
custom providers via the UI.

## Boundaries

- **Metadata-only**: the registry never executes a provider, never opens
  a network socket, never imports the provider's runtime.
- **No model auto-download** anywhere. `ALLOW_MODEL_AUTODOWNLOAD` stays
  `false` and is reserved for a future explicit fetch helper.
- **No secrets** in provider records. API keys are not surfaced even
  when their env vars are set; endpoint URLs are returned without any
  credential portion.
- **No package installs from the UI.** Custom providers register
  metadata only; runtime install / configuration is still an operator
  task.

## Five categories

| Category | Examples | Notes |
|---|---|---|
| `llm` | `template`, `mock`, `ollama`, `vllm`, `openai_compatible`, `openai`, `anthropic`, `local_http` | Network providers gated by `SCRIPTWRITER_ENABLE_NETWORK_CALLS`. |
| `tts` | `piper`, `coqui_tts`, `xtts`, `styletts`, `elevenlabs_compatible`, `openai_compatible_tts`, `local_http_tts` | Phase 5A wires `piper`. The rest are operator-installable stubs. |
| `video_generator` | `sadtalker`, `musetalk`, `wav2lip`, `liveportrait`, `local_http_video`, `external_video_api` | All `not_implemented`. GPU-bound providers carry `requires_gpu=true`. |
| `audio_processor` | `ffmpeg_convert`, `ffmpeg_loudness_normalize`, `ffmpeg_trim_silence`, `future_denoise`, `future_vad` | `ffmpeg_convert` is `available` when the image has ffmpeg (Phase 4F). |
| `image_processor` | `stdlib_image_validation`, `future_face_cropper`, `future_background_removal`, `future_quality_checker`, `future_identity_guard_extension` | `stdlib_image_validation` is `available` (Phase 3E hand-rolled header parser). |

## ProviderInfo fields

```python
class ProviderInfo:
    category: ProviderCategory                # llm | tts | video_generator | audio_processor | image_processor
    provider_id: str                          # slug, e.g. "piper"
    label: str                                # human-readable
    backend_type: str                         # e.g. "piper", "local_http"
    default_model: str | None
    is_local: bool                            # legacy mirror of local_or_external
    status: ProviderStatusValue               # available | configured | not_configured | not_implemented | disabled | error
    notes: str
    # Phase 6D additions:
    local_or_external: "local" | "external"
    supported_models: list[str]
    requires_network: bool
    requires_gpu: bool
    requires_model_files: bool
    healthcheck_available: bool
    warning: str
    docs_url: str
    is_custom: bool                           # frontend custom providers only
```

## API endpoints

| Method | Path | Returns |
|---|---|---|
| GET | `/api/v1/providers` | All five categories in one payload |
| GET | `/api/v1/providers/llm` | LLM-only list |
| GET | `/api/v1/providers/tts` | TTS-only list |
| GET | `/api/v1/providers/video-generators` | Video-only list |
| GET | `/api/v1/providers/audio-processors` | Audio-processor list |
| GET | `/api/v1/providers/image-processors` | Image-processor list |
| GET | `/api/v1/providers/{category}/{provider_id}` | Single provider; 404 on unknown category or id |

Both URL-style slugs (`video-generators`) and snake_case category names
(`video_generator`) work for the per-provider lookup.

## Custom providers (UI-only)

The Settings panel (right sidebar + `/settings`) has a **Custom
providers** section that lets the operator register metadata for any
provider not in the built-in catalog. Behaviour:

- Stored in `localStorage` under `aivideo:custom-providers:v1`.
- **Slug-safe `provider_id` only** — `^[a-z0-9][a-z0-9_-]{0,79}$`.
- **No credentials** accepted. URLs containing `@` or
  `Authorization` / `api_key` / `token=` are refused at validation time.
- Custom providers are merged into the per-job dropdowns with a
  `custom · metadata only` badge.
- Built-in providers always win on ID collision (no shadow override).
- The form clearly states: "Adding a custom provider here only
  registers metadata for selection. You still need to install and
  configure the runtime separately."

Custom-provider lifecycle events are logged on the right-sidebar Logs
panel:

- `custom provider added: <category>/<provider_id>`
- `custom provider deleted: <category>/<provider_id>`

No backend file is touched. No shell command runs. No package is
installed.

## Per-job provider/tool selection

`POST /api/v1/jobs` and `PATCH /api/v1/jobs/{id}` accept a
`provider_selection` JSON object with these whitelisted keys:

```jsonc
{
  "script_provider_id":  "template",
  "script_model":        null,
  "tts_provider_id":     "piper",
  "tts_model":           "en_US-amy-medium",
  "video_provider_id":   "sadtalker",
  "video_model":         null,
  "audio_processor_id":  "ffmpeg_convert",
  "image_processor_id":  "stdlib_image_validation"
}
```

- Unknown provider IDs are accepted at write time (the runtime is the
  gate; jobs can carry forward-looking IDs for future-phase runtimes).
- Unknown *keys* are rejected (`extra="forbid"`).

The CreateJobForm renders one dropdown per category, prefilled from
Settings defaults. Each option shows status + GPU/network/custom flags.

## Tests

`tests/integration/test_phase6d_provider_registry.py` (21 tests) pins
the contract: all five categories present; required Phase 6D fields on
every record; ffmpeg_convert + stdlib_image_validation present; GPU
video placeholders carry `requires_gpu=true`; API keys + endpoint
credentials never leak; per-provider lookup returns 404 on unknown;
`ProviderSelection` accepts the two new keys on create + patch;
future / unknown provider IDs accepted at write time; registry + API
modules import with zero of `torch` / `diffusers` / `transformers` /
`accelerate` / `openai` / `anthropic` / `httpx` / `aiohttp` /
`sadtalker` / `musetalk` / `wav2lip` / `liveportrait` / `piper` in
`sys.modules`.

Run with: `make phase6d-test`.

## Phase 7A: GPU isolation invariants for the video catalog

Phase 7A pins, but does not implement, the GPU surface. The relevant
guarantees:

- `requires_gpu` / `requires_model_files` are honest for every video
  provider (`sadtalker`, `musetalk`, `wav2lip`, `liveportrait` →
  `true/true`; `local_http_video`, `external_video_api` → `false/false`).
- `/api/v1/video/generate` still returns metadata-only
  `not_implemented` for the four GPU placeholders and `not_configured`
  for `liveportrait`.
- The default backend image and the agents base wheel still import
  cleanly without pulling torch / diffusers / transformers / xformers
  / sadtalker / musetalk / wav2lip / liveportrait into `sys.modules`.

Run with: `make phase7a-test`. Pair with `make docker-gpu-config-check`
+ `make docker-gpu-smoke` for the host audit. See
[`gpu-runtime.md`](gpu-runtime.md) and [`video-providers.md`](video-providers.md).

## What's intentionally NOT in Phase 6D

- Real video generation.
- Real lip-sync.
- SadTalker / MuseTalk / Wav2Lip / LivePortrait inference.
- Whisper / WhisperX.
- C2PA signing.
- External publishing.
- GPU image builds.
- Model weight downloads.
- Backend custom-provider persistence — custom providers live in the
  browser's localStorage only.
- Shell execution from the browser.
- Package installation from the UI.
