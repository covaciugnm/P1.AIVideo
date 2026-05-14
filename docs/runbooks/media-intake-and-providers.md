# Media intake & providers (Phase 4F)

This runbook covers the operator-facing additions in Phase 4F: provider
catalog + per-job provider selection, the TTS preview hook, audio
playback through the artifact content endpoint, expanded audio upload
formats, and image preview.

## Providers

Three categories are exposed at `/api/v1/providers`:

- **LLM (script generation)** — backed by the scriptwriter registry
  (`template`, `mock`, `ollama`, `vllm`, `openai_compatible`, `openai`,
  `anthropic`, `local_http`). Only `template` and `mock` are guaranteed
  to be `available`. Network-call providers stay `not_implemented` until
  `SCRIPTWRITER_ENABLE_NETWORK_CALLS=true` and Phase 4F+ wires
  generation.
- **TTS** — Phase 3B's `piper`. Status is `not_configured` unless the
  `piper-tts` Python package is installed AND `PIPER_MODELS_ROOT` is set
  with a voice on disk.
- **Video generator** — `sadtalker`, `musetalk`, `wav2lip`. All
  `not_implemented` until Phase 5/6.

The endpoint returns metadata only — no API keys, no endpoint URLs with
embedded tokens, no secrets. The operator can pick a per-category
default in **Settings → Providers**; the choice prefills the create-job
form and is persisted in `localStorage`. Per-job dropdowns let the
operator override the default at submission time.

## Per-job provider selection

The job schema carries an optional `provider_selection` JSON column with
six whitelisted fields:

```json
{
  "script_provider_id": "template",
  "script_model": null,
  "tts_provider_id": "piper",
  "tts_model": "en_US-amy-medium",
  "video_provider_id": "sadtalker",
  "video_model": null
}
```

All fields are optional and unknown keys are rejected (`extra="forbid"`).
The orchestrator's stage handlers can read this dict via `Job.provider_selection`
and fall back to their configured defaults when a field is `None`.

## TTS generate / Listen

Create-job page exposes:

- **Generate audio** — `POST /api/v1/tts/generate { script_text, tts_provider_id }`.
  In light mode this always returns `503 { code: "tts_provider_not_configured" }`
  surfaced inline as a yellow warning ("Provider 'piper' is not configured.
  Install the runtime + place voice assets, then enable in Settings.").
  No fake audio is produced. Phase 5+ will plug a real runtime into the
  voice stage and this preview endpoint can then delegate.
- **Listen** — for uploaded audio (provided-audio flow) and any future
  generated audio, the page renders an HTML5 `<audio controls>` pointing
  at `GET /api/v1/artifacts/{id}/content`.

## Artifact content endpoint

`GET /api/v1/artifacts/{artifact_id}/content` streams the binary
backing an artifact row. Guards:

- Artifact must exist in the DB → 404.
- Artifact type must be one of `{audio, image, script}` → 415 otherwise.
- `local_path` must resolve to a real file → 404 if missing.
- Resolved path must live under one of the configured allowed roots
  (`PROVIDED_AUDIO_ALLOWED_ROOTS`, `PROVIDED_IMAGE_ALLOWED_ROOTS`, or
  the three upload roots) → 403 if outside.
- Path-traversal markers (`..` segments) rejected before resolution → 403.

The response uses `FileResponse` with the artifact's recorded `mime_type`
and `Content-Disposition: inline`. No path is echoed in headers or body.

## Audio upload formats

`POST /api/v1/uploads/audio` accepts `.wav`, `.mp3`, `.m4a`, `.aac`,
`.flac`, `.ogg`. Behaviour:

- **WAV** input: validated via the Phase 3D `wave`-stdlib inspector;
  registered as-is.
- **Non-WAV** input with `ffmpeg` on PATH: transcoded to mono PCM WAV at
  22050 Hz alongside the original. The registered artifact's `local_path`
  points at the converted WAV; the original file is kept on disk and its
  path is recorded in `metadata_json["original_local_path"]`.
- **Non-WAV** input without ffmpeg: stored as-is, registered with
  `metadata_json["needs_conversion"]=True` and
  `metadata_json["ffmpeg_available"]=False`. Downstream stages will
  refuse to process it; the operator gets a clear hint to install
  ffmpeg.
- Bad extension → 400 with `extension` in the detail string. Failed
  ffmpeg transcode → 400 with `audio_conversion_failed: …` detail.

The light Docker image installs `ffmpeg` (Debian apt package — pulls in
`ffprobe`) so the happy path works there. For non-Docker dev, install
ffmpeg via your system package manager:

```bash
sudo apt install ffmpeg            # Debian / Ubuntu
brew install ffmpeg                # macOS
```

ffmpeg is bounded to audio decode/mux by the conversion service; no
video pipeline yet.

## Image upload

Phase 3E already accepted PNG / JPEG / WebP via a hand-rolled header
parser. Phase 4F adds an in-page preview after upload (HTML5 `<img>` with
`src` pointing at the artifact content URL).

## Minimum quality guidance (UI hints)

The create-job page now surfaces inline quality hints:

- **Audio** — accepted extensions, target ≥ 22050 Hz, mono or stereo,
  ≥ 1 s, max size from `AUDIO_MAX_FILE_SIZE_BYTES`, must be synthetic
  or owned.
- **Image** — PNG/JPEG/WebP, ≥ 512×512 recommended, 1024×1024+ preferred,
  front-facing, well-lit, synthetic-only.

These are guidance only — the existing validators (header sanity, size
cap) remain the hard gates.

## Settings → Providers section

A new section in the right-sidebar Settings panel (and on
`/settings`) renders:

- One row per provider with status badge, default model, locality, and
  notes.
- A per-category "default provider" dropdown stored in `localStorage`
  (`defaultLlmProvider`, `defaultTtsProvider`, `defaultVideoProvider`).
- A **Test** button on TTS rows that exercises `/tts/generate` and
  surfaces the 503 message inline.

There is no "Add provider package" dialog yet — adding a provider
requires installing its runtime on the host + setting env vars (see the
relevant provider's docs). That dialog is a Phase 4G follow-up.

## What is intentionally NOT in Phase 4F

- Real TTS synthesis — `/tts/generate` is always 503.
- Real video generation — `sadtalker`/`musetalk`/`wav2lip` stay
  `not_implemented`.
- Real lip-sync inference.
- C2PA signing / external publishing.
- Browser-driven Docker control or shell execution.
- Model weight auto-downloads.
- WebSocket/SSE log streaming.
