# P1.AIVideo

Docker-based multi-agent pipeline that produces short vertical reels (15–60s) featuring a **fully synthetic** white Caucasian human performing lip-synced narration from a text brief.

> **Current status: Phase 3I — QC contract + structured report artifact.**
>
> - **`QCReport` / `QCCheck` / `QCDecisionType`** added to `common.schemas`. The report carries `passed: bool`, a list of named checks, the upstream artifact URIs + checksums (script / edit_plan / reel_draft), `target_duration_seconds`, `segment_count`, and `expected_segments`.
> - **QC handler rewritten** to consume the editor's `edit_plan` + `reel_draft` plus the scriptwriter's `script` artifact, and run four structural checks: `script_artifact_present`, `segments_present`, `total_duration_matches_target`, `reel_draft_is_stub`. Missing required artifacts raise `StageRejection`; content-level problems produce a `QCReport` with `passed=False`.
> - The QC report is registered as **`ArtifactType.metadata`** (mime `application/json`, content SHA-256) so downstream stages — and future audit tooling — can pull it from the `artifacts` table by job id.
> - **No real media inspected.** No `ffmpeg`, `ffprobe`, `mediainfo`, `moviepy`, `OpenCV`, `imageio`, `numpy`, `PIL`, `torch`, etc. A subprocess audit asserts the QC module imports none of them.
> - **11 Phase 3I tests** cover the happy path, three structural rejections, three content-level failure modes (incomplete segments, total mismatch, reel_draft with local_path), determinism, end-to-end DAG promoting the report into the artifacts table, and the no-heavy-imports invariant.
>
> **No real video / audio QC. No ffmpeg / ffprobe / mediainfo / moviepy / OpenCV / imageio / numpy / PIL / torch added. No model weights downloaded. No SadTalker / Whisper / SDXL / lip-sync / face generation implemented.**

> **Previous milestone: Phase 3E — image input validation + face artifact contract.**
> Phase 3D (audio validation + artifact registry) plus a symmetric path for face images:
>
> - **`common/image_validation.py`** — stdlib-only header parsing for **PNG / JPEG / WebP** (VP8 / VP8L / VP8X variants). Returns `(width, height, size, sha256, format)` with no Pillow / OpenCV / imageio / numpy.
> - **`ImageRef`** schema with the same compliance shape as `AudioRef`: both `consent_confirmed` and `synthetic_person_confirmed` must be `true`; path safety against `$PROVIDED_IMAGE_ALLOWED_ROOTS`; only `image/png` / `image/jpeg` / `image/webp` mime types.
> - **`face_mode`** added to `JobCreateRequest` (optional). When set to `"provided_image"`, `image_ref` is required and the face handler validates + emits an `ArtifactRef` with real `width` / `height` / `size_bytes` / `checksum_sha256` / `mime_type`. The DAG runner promotes it into the `artifacts` table just like audio.
> - **`ArtifactType` enum** (`common/enums.py`) — `audio` / `image` / `script` / `video` / `metadata` / `final_export`. Used by the new face artifact registration; existing handlers keep their string literals (no large refactor).
> - **`Artifact` model** gains `width` and `height` columns (None for non-image artifacts).
> - **Compliance event** records `extra={"voice_source": ..., "face_source": "provided_image" | "stub"}`.
>
> **No SDXL. No face generation. No identity / celebrity matching. No SadTalker. No real lip-sync. No Whisper. No torch / torchvision / torchaudio / Pillow / OpenCV / imageio / numpy / diffusers / transformers added. No model weights downloaded. No voice cloning.** See [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) for the full multi-phase plan.

## Hard guarantees

- **Synthetic-only persona.** Faces and voices are generated; no real-person likeness or voice is ever cloned.
- **Mandatory disclosure.** Every output ships with a visible "AI-generated" overlay, a C2PA manifest, and XMP/EXIF flags.
- **Fully local.** Runs in Docker with GPU support; no paid APIs required at any pipeline stage.
- **No surprise downloads.** Model weights are never auto-fetched at build or first run. See [`docs/runbooks/model-management.md`](docs/runbooks/model-management.md).
- **Adapter-pattern model integrations.** Lip-sync (and other model backends) are swappable via env vars — `LIPSYNC_BACKEND=sadtalker` is the v1 default. See [`docs/architecture/lipsync-adapter.md`](docs/architecture/lipsync-adapter.md).

## Prerequisites

- **Docker Engine** (≥ 24) with **Docker Compose v2**.
- **Linux host** (Ubuntu 22.04+ recommended).
- For GPU-enabled services:
  - **NVIDIA proprietary driver** (≥ 550) on the host.
  - **NVIDIA Container Toolkit** so Docker can attach GPUs to containers.
  - Verify with `nvidia-smi` on the host. Setup steps live in [`docs/runbooks/gpu-docker.md`](docs/runbooks/gpu-docker.md).
- **Model weights** live on the host under `./models/` and are bind-mounted into containers. No weights are auto-downloaded; see [`docs/runbooks/model-management.md`](docs/runbooks/model-management.md).
- Copy `.env.example` to `.env` before bringing up the stack.

## Top-level layout

```
docs/        Architecture, compliance, runbooks, full project plan
docker/      Dockerfiles per service + compose overlays
backend/     FastAPI app (jobs, auth, artifacts)
frontend/    Next.js dashboard
agents/      One subfolder per specialist agent (script, voice, face, lipsync, ...)
pipelines/   DAG definitions
models/      Local model weights (gitignored) + model cards
assets/      Licensed/synthetic assets only (fonts, music, b-roll, overlays)
scripts/     CLI helpers (model downloaders, seed scripts, e2e runners)
storage/     Local dev mounts for MinIO + Postgres (gitignored)
tests/       Cross-cutting integration & e2e
configs/     Prompt templates, voice profiles, personas, policy rules
```

## Where to start

1. Read [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) — full technical plan.
2. Read [`docs/architecture/overview.md`](docs/architecture/overview.md) — system architecture.
3. Read [`docs/compliance/policy.md`](docs/compliance/policy.md) — what this system will and will not do.
4. Read [`docs/runbooks/dev-setup.md`](docs/runbooks/dev-setup.md) — Phase 1 quickstart (install Python deps, run the integration test).
5. Read [`docs/runbooks/gpu-docker.md`](docs/runbooks/gpu-docker.md) — host setup for NVIDIA + Docker (only needed once Phase 3 ships).
6. Copy `.env.example` to `.env` and adjust paths.

## Phase 3I scope — current

Implemented on top of Phase 3H:

- **`QCDecisionType`**, **`QCCheck`**, and **`QCReport`** added to `common.schemas`.
- **`agents/qc/handler.py`** rewritten:
  - Pulls `edit_plan` + `reel_draft` from the editor stage's output and `script` from the scriptwriter stage's output.
  - Missing required artifacts → `StageRejection` (wiring failure).
  - Runs four named checks:
    - `script_artifact_present` — script ref carries a content checksum.
    - `segments_present` — edit_plan has the three expected types in order: hook, body, cta.
    - `total_duration_matches_target` — segment durations sum (in ms, 1 ms tolerance) to `target_duration_seconds`.
    - `reel_draft_is_stub` — reel_draft is still a Phase 3H stub (s3:// URI, no local_path); a local file triggers a `warn`.
  - Aggregate `passed = True` iff every check is `pass`.
  - Emits a `QCReport` artifact (`ArtifactType.metadata`, mime `application/json`, content SHA-256) with `extra["qc_report"]` carrying the structured report and `extra["qc_passed"]` for cheap downstream filtering.
- **11 Phase 3I tests** in `tests/integration/test_phase3i_qc_report.py`:
  - 2 happy-path tests (artifact shape + checksum + determinism).
  - 3 structural rejection tests (missing edit_plan / reel_draft / script).
  - 4 content-level failure tests (incomplete segments → `segments_present` fails; total mismatch → `total_duration_matches_target` fails; reel_draft with `local_path` → `reel_draft_is_stub` warns; stub reel_draft passes).
  - 1 end-to-end DAG test verifying the metadata artifact lands in the `artifacts` table with the right shape.
  - 1 subprocess-isolated import audit confirming no `ffmpeg` / `ffprobe` / `mediainfo` / `moviepy` / `cv2` / `imageio` / `numpy` / `PIL` / `torch` / `diffusers` / `transformers` / `soundfile` / `librosa` is pulled in.

Explicitly **not** in Phase 3I:

- **No real video / audio QC.** Every check operates on artifact metadata; no file is opened.
- **No `ffmpeg` / `ffprobe` / `mediainfo` / `moviepy` / `OpenCV` / `imageio` / `numpy` / `PIL` added.**
- **No SadTalker / Whisper / SDXL / real lip-sync / face generation.**
- **No model weights downloaded.**
- **No Docker builds run.**

## Phase 3H scope (still active)

Implemented on top of Phase 3G:

- **`ArtifactType.edit_plan`** added to `common.enums` (7 values now).
- **`EditSegment`** and **`EditPlan`** Pydantic schemas in `common.schemas`. Strict validators:
  - per-segment `end - start == duration` (compared in ms, so float ops don't break it);
  - per-plan: sum of segment durations equals `target_duration_seconds`, and segments tile from 0 to the target without gaps or overlaps.
- **Editor handler rewritten** (`agents/editor/handler.py`):
  - Reads the structured script from the scriptwriter stage output (`state.stage_outputs["scriptwriter"].artifacts["script"].extra["structured_script"]`).
  - Allocates `target_duration_seconds` as 20% / 65% / 15% across hook / body / cta. Allocation is done in **milliseconds** so segments sum exactly to the target for any reasonable target duration (30s, 33s, 45s, etc.).
  - Builds an `EditPlan` with three segments, serializes it to JSON, computes a content SHA-256, and emits an `ArtifactType.edit_plan` artifact whose `extra["edit_plan"]` carries the full plan, the source script URI + checksum, and a `no_video_generated: true` flag.
  - Keeps the existing `reel_draft.mp4` stub in the output (downstream QC still checks for it), now cross-referencing the edit plan.
- **14 Phase 3H tests** in `tests/integration/test_phase3h_editor_plan.py`:
  - 5 schema-level tests covering mismatched durations, negative starts, end-before-start, total mismatch, gap-between-segments.
  - 8 editor handler tests: happy path artifact shape, segment percentages exact, reel_draft stub preserved, deterministic same-input output, non-integer target (33s) tiles exactly, missing scriptwriter rejects, missing `structured_script` rejects, no files written to disk.
  - 1 end-to-end DAG test promoting the `edit_plan` row into the `artifacts` table with mime `application/json`, content checksum, and source-script back-references.
  - 1 subprocess-isolated check that importing the editor handler doesn't pull in `ffmpeg` / `moviepy` / `cv2` / `imageio` / `numpy` / `PIL` / `torch` / `diffusers` / `transformers`.

Explicitly **not** in Phase 3H:

- **No real video editing.** Editor remains metadata-only; the URI on the `edit_plan` artifact is an `s3://` stub.
- **No `ffmpeg` / `moviepy` / `OpenCV` / `imageio` / `numpy` / `PIL` added.**
- **No SadTalker / Whisper / SDXL / real lip-sync / face generation.**
- **No model weights downloaded.**
- **No Docker builds run.**

## Phase 3G scope (still active)

Implemented on top of Phase 3F:

- **`agents/scriptwriter/core/provider.py`** — `ScriptProvider` ABC with `provider_name`, `model_name`, `supports_streaming`, `supports_json_mode`, `required_config()`, `healthcheck()`, `generate()`. Plus the structured `ScriptRequest` and `ScriptResult` Pydantic models (hook / body / cta / full_script / estimated_duration_seconds / language / provider / model / prompt_version / metadata).
- **`agents/scriptwriter/core/registry.py`** — `resolve(name)` lazy-imports providers; `known_backends()` advertises the eight names. Unknown backends raise `UnsupportedBackendError`.
- **Template provider** (`agents/scriptwriter/providers/template/provider.py`) — deterministic, dependency-free, produces a structured script from `script_text` (paragraph-split) or from `brief` (placeholder). Default Phase 3G backend.
- **Six stub providers** (`ollama`, `vllm`, `openai_compatible`, `openai`, `anthropic`, `local_http`) — each reads its env config, returns `not_configured` / `not_implemented` from `healthcheck()`, and raises `ProviderNotImplementedError` from `generate()`. Zero external client imports — verified by subprocess audit.
- **DAG handler** wired through the registry. Default backend `template`; configured non-template backends fall back to `template` unless `SCRIPTWRITER_ENABLE_NETWORK_CALLS=true` AND the provider succeeds. Failure of a real provider also falls back, so the DAG keeps moving.
- **Script artifact** carries `ArtifactType.script.value`, a SHA-256 of the serialized structured script, and the `structured_script` dict in `metadata_json` — promoted to the `artifacts` table.
- **Configuration**:
  - `.env.example` block: `SCRIPTWRITER_BACKEND=template`, `SCRIPTWRITER_MODEL=qwen3.6`, `SCRIPTWRITER_FALLBACK_MODEL=qwen3:8b`, `SCRIPTWRITER_ALLOWED_BACKENDS=...`, `SCRIPTWRITER_ENABLE_NETWORK_CALLS=false`, plus per-provider blocks for Ollama / vLLM / OpenAI-compatible / OpenAI / Anthropic / local_http and `LLM_MODEL_REGISTRY_JSON` / `LLM_PROVIDER_CONFIG_PATH`.
  - `configs/llm/providers.example.yaml` — operators copy this and add models/providers without touching code.
- **28 Phase 3G tests** in `tests/integration/test_phase3g_scriptwriter_contracts.py`.

Explicitly **not** in Phase 3G:

- **No real LLM calls.** Every non-template provider's `generate()` raises `ProviderNotImplementedError`.
- **No OpenAI / Anthropic / LangChain / LangGraph / Transformers / Torch / Diffusers added.** Verified twice (Phase 3F + Phase 3G subprocess tests).
- **No HTTP client (`httpx`, `requests`, `aiohttp`) imported at module load.**
- **No API keys required.**
- **No model weights downloaded.**
- **No SadTalker / Whisper / SDXL / real lip-sync / video / face generation.**
- **No Docker builds run.**

## Phase 3F scope (still active)

Structural / test-only cleanup. No new providers, no new features.

- **`agents/pyproject.toml`** — uses `package-dir = {"agents": "."}` plus an enumerated list of all 18 subpackages (`compliance_officer`, `orchestrator`, `scriptwriter`, `voice` + `voice.core` + `voice.providers` + `voice.providers.piper`, `face`, `editor`, `qc`, `publisher`, `lipsync` + `lipsync.core` + `lipsync.providers` + `lipsync.providers.{sadtalker,musetalk,wav2lip}`). Bumped to version `0.3.0`.
- **`tests/conftest.py`** — no longer touches `sys.path`. Only sets test env defaults (`DATABASE_URL`, `APP_ENV`, `LOG_LEVEL`, `COMPLIANCE_SIGNING_KEY`). The previous project-root + backend/ entries are gone.
- **`ArtifactType` enum (`common.enums`)** — six members: `audio`, `image`, `script`, `video`, `metadata`, `final_export`. Voice + face handlers now emit `artifact_type=ArtifactType.<name>.value`. The enum inherits from `str` so legacy code comparing the column to bare strings keeps working.
- **`tests/integration/test_phase3f_packaging_contracts.py`** — 10 packaging-contract tests, four of them subprocess-isolated with `PYTHONPATH` explicitly stripped. Proves the package graph works without any test-only hacks AND that the `agents.*` tree pulls in zero LLM / ML libraries.

Explicitly **not** in Phase 3F:

- **No Scriptwriter / LLM provider implemented.** No `openai`, `langchain`, `langgraph`, `transformers`, `torch`, `diffusers`, `accelerate`, `xformers`, `whisper` added.
- **No SadTalker / lip-sync / SDXL / face-generation / Whisper changes.**
- **No model weights downloaded.**
- **No Docker builds.**
- **No refactor of historical artifact_type literals.** Scriptwriter, lipsync, editor, qc, publisher keep their `"audio"` / `"video"` / `"json"` strings — they're enum-compatible because `ArtifactType` is `str`-derived, and the user spec called the broader refactor "out of scope".

## Phase 3E scope (still active)

Implemented on top of Phase 3D:

- **`common/image_validation.py`** — `validate_and_inspect_image(path, *, mime_type, max_size_bytes=None, min_width=None, min_height=None) -> ImageMetadata`. Hand-rolled header parsers:
  - **PNG**: 8-byte signature + IHDR width/height (24 bytes total).
  - **JPEG**: walks markers until SOF0..SOF15 (excluding DHT/JPG/DAC) and reads height/width from the segment.
  - **WebP**: walks RIFF chunks; supports VP8X (extended), VP8L (lossless), VP8 (lossy) — each variant decoded per its packed format.
- **`ImageRef`** in `common/schemas.py` — `type` (`local_path` | `artifact_uri`), `path`, `mime_type` (`image/png` | `image/jpeg` | `image/webp`), `checksum`, `consent_confirmed` (must be `true`), `synthetic_person_confirmed` (must be `true`). Path safety enforced via `validate_local_image_path`.
- **`face_mode`** + **`image_ref`** added to `JobCreateRequest` / `Job` / `DagState`. `face_mode` is **optional** with no default — jobs that don't opt in keep the existing Phase 2 stub face handler. When explicitly set to `"provided_image"`, `image_ref` is required.
- **Face handler** routes by `face_mode`: stub (default) or `provided_image` (validate + emit populated `ArtifactRef`).
- **`ArtifactType` enum** — `audio` / `image` / `script` / `video` / `metadata` / `final_export`. Used by the new face artifact registration. De-duplication is documented as a future optimization.
- **`Artifact` model** — new `width` and `height` columns.
- **`ArtifactRef`** — gains `mime_type` (top-level), `width`, `height`.
- **`common/path_safety.py`** — refactored to a shared `_validate_local_path` helper used by both audio and image; new `validate_local_image_path` + `get_allowed_image_roots`.
- **Compliance event extra** — `face_source` records `"provided_image"` or `"stub"`.
- **Config** — `PROVIDED_IMAGE_ALLOWED_ROOTS`, `IMAGE_MAX_FILE_SIZE_BYTES` (10 MB default), optional `IMAGE_MIN_WIDTH` / `IMAGE_MIN_HEIGHT`.
- **22 Phase 3E tests** — unit-level coverage of `validate_and_inspect_image` (PNG / JPEG / WebP happy path, missing file, bad header, oversize, unsupported mime, min-dimension enforcement), end-to-end DAG tests (provided_image creates an artifact row with correct width/height; default mode records `face_source="stub"` and creates no image artifact; bad header rejects at face stage; oversize rejects at face stage; metadata-only invariant on artifact rows), and a subprocess-isolated check that no image-ML library is pulled in.

Explicitly **not** in Phase 3E:

- **No SDXL / face generation.**
- **No identity / celebrity / public-figure matching.** The CLIP-NN identity guard documented in `docs/compliance/identity-guard.md` is still deferred. Operator consent flags are the only compliance signal for provided images.
- **No SadTalker / real lip-sync.**
- **No Whisper / LLM script generation.**
- **No torch / torchvision / torchaudio / Pillow / OpenCV / imageio / numpy / diffusers / transformers / accelerate / xformers / gfpgan added.**
- **No model weights downloaded.**
- **No voice cloning.**
- **No artifact deduplication.** A future optimization may dedupe by `checksum_sha256` across jobs; Phase 3E does not.

## Phase 3D scope (still active)

Implemented on top of Phase 3C:

- **`common/audio_validation.py`** — `validate_and_inspect_wav(path, *, mime_type, max_size_bytes=None, allowed_sample_rates=None, allowed_channels=None)` returns an `AudioMetadata` dataclass on success. Stdlib-only.
- **`Artifact` model** (`backend/app/models/artifact.py`) — `artifacts` table with the spec fields; uses `metadata_json` (not `metadata`) to dodge the SQLAlchemy reserved name.
- **`artifact_service`** — `register_artifact` + `register_artifact_ref` + `list_for_job`.
- **Voice handler** — for `voice_mode="provided_audio"` with `type="local_path"`, runs the audio validator and emits a fully-populated `ArtifactRef`. On invalid header / size / sample rate / channels, the stage is rejected (the job moves to `rejected`); no Artifact row is created.
- **DAG runner** — `_record_stage_success` now promotes any `ArtifactRef` with `checksum_sha256` set into the `artifacts` table, linking the row to the originating `stage_run_id`. Stubs are not promoted.
- **`ArtifactRef` schema** — `kind` → `artifact_type`, `sha256` → `checksum_sha256`; added `local_path`, `duration_seconds`, `sample_rate`, `channels`.
- **Config** — `AUDIO_MAX_FILE_SIZE_BYTES` (50 MB default), `AUDIO_ALLOWED_SAMPLE_RATES`, `AUDIO_ALLOWED_CHANNELS`, `ARTIFACTS_LOCAL_ROOT` added.
- **13 Phase 3D tests** — unit-level coverage of `validate_and_inspect_wav` (valid file, missing file, bad header, oversize, unsupported mime, disallowed sample-rate / channels), end-to-end DAG tests (provided_audio creates artifact row with correct extracted metadata; TTS does NOT create an audio artifact; bad WAV rejects at the voice stage; oversize rejects at the voice stage; metadata-only invariant on artifact rows), and a subprocess-isolated check that no audio-ML library is pulled in.

Explicitly **not** in Phase 3D:

- **No Whisper / transcription / alignment.** No `whisper`, `whisperx`, or any speech-to-text library.
- **No SadTalker / real lip-sync changes.**
- **No SDXL / face generation.**
- **No torch / torchvision / torchaudio / diffusers / transformers / accelerate / xformers / gfpgan added.**
- **No ffmpeg / ffprobe** invocations. WAV inspection uses stdlib `wave` exclusively.
- **No model weights downloaded.**
- **No voice cloning.** The schema still refuses any `synthetic_or_owned_voice=False`.
- **No copy / transcode** of provided audio. The file stays where the operator placed it; the registry just records a `file://` URI + metadata.

## Phase 3C scope (still active)

Implemented on top of Phase 3B:

- **`voice_mode`** added to `JobCreateRequest` (`"tts"` default, `"provided_audio"` opt-in).
- **`AudioRef`** (`common/schemas.py`) — typed reference to an operator-supplied `.wav`. Fields: `type` (`local_path` | `artifact_uri`), `path`, `mime_type` (`audio/wav` | `audio/x-wav`), `duration_seconds`, `checksum`, `consent_confirmed`, `synthetic_or_owned_voice`. Validators refuse anything but `true` on both consent flags.
- **Path safety** (`common/path_safety.py`) — `local_path` audio refs must be absolute, free of `..` segments, end in `.wav`, and resolve under one of the directories listed in `$PROVIDED_AUDIO_ALLOWED_ROOTS`. Validation is re-applied at the voice handler as defense-in-depth.
- **Voice handler routes by mode.** `tts` → existing Phase 2 no-op (preserves all previous tests); `provided_audio` → validates + emits `ArtifactRef` with a `file://` URI pointing at the operator's file. Never reads bytes; never transcodes.
- **Compliance audit** — the `policy_gate` event row gains an `extra` JSON column carrying `{"voice_source": "tts" | "provided_audio"}`.
- **Job DB** — `Job` model gains `voice_mode`, `script_text`, `tts_backend`, and `audio_ref` (JSON) columns. `JobResponse` exposes them.
- 13 Phase 3C tests covering schema validation (8 failure modes + happy path), end-to-end DAG runs for both modes, and a subprocess-isolated check that no heavy audio/ML library is pulled in by importing the voice handler.

Explicitly **not** in Phase 3C:

- **No torch / torchvision / torchaudio / diffusers / transformers / accelerate / xformers / gfpgan / SDXL / SadTalker / MuseTalk / Wav2Lip dependencies.**
- **No real lip-sync, no face generation, no SDXL.** All three lip-sync providers + SadTalker are unchanged.
- **No voice cloning.** Hard-coded: the schema refuses `synthetic_or_owned_voice=False`.
- **No external paid APIs.**
- **No DAG wiring of the real Piper provider.** The Phase 3B lazy-import provider remains standalone; the TTS branch of the voice handler is still a no-op stub.
- **No `ffprobe` or real audio validation.** Duration/checksum are recorded verbatim from the operator's declaration; a future phase can add deeper validation.

## Phase 3B (narrow) scope — still active

Implemented on top of Phase 3A:

- **Piper provider's `synthesize()` is now real.** When `piper` is installed and the voice assets are on disk, it loads the voice and writes a WAV via the standard library's `wave` module. The output path is either explicit (`VoiceRequest.output_path`) or a tempfile.
- **Lazy import.** `agents.voice.providers.piper.provider` does **not** import `piper` at module load. The import happens inside `synthesize()` after the assets check. A subprocess-isolated test asserts that importing the provider module does not pull in `piper`, `torch`, `onnxruntime`, `transformers`, or `diffusers`.
- **No auto-download.** Operators place `.onnx` + `.onnx.json` manually under `$PIPER_MODELS_ROOT`. The `ALLOW_MODEL_AUTODOWNLOAD` flag is intentionally not honored at runtime — a future explicit fetch helper will own that.
- **`PiperProvider.healthcheck()`** now reports `piper_runtime_installed` in its `extra` dict so an operator-level healthcheck shows both asset status and runtime availability.
- **5 Phase 3B tests** in `tests/integration/test_phase3b_piper.py` — all pass without `piper` installed; the real-TTS smoke test is skipped unless both `piper` and `$PIPER_TEST_VOICE_ROOT` are provided.

Explicitly **not** in Phase 3B (narrow):

- **No torch / torchvision / torchaudio.**
- **No SadTalker implementation.** SadTalker remains the Phase 3A stub.
- **No real lip-sync.** All three lip-sync providers (SadTalker / MuseTalk / Wav2Lip) still raise `ProviderNotImplementedError` from `synthesize()`.
- **No model weights downloaded.** `piper-tts` itself is not added as a hard dependency in any pyproject.toml.
- **No DAG wiring.** The Phase 2 no-op voice + lipsync DAG handlers are untouched. Wiring the Piper provider into the voice DAG stage is deferred.
- **No external paid APIs.**

## Phase 3A scope (still active)

Implemented on top of Phase 2:

- `LipSyncProvider` and `VoiceProvider` abstract contracts (`agents/lipsync/core/provider.py`, `agents/voice/core/provider.py`) with `required_assets()`, `healthcheck()`, `synthesize()` — plus `validate_compliance_token()` for LipSync.
- `AssetSpec` + `ProviderHealth` + `ProviderHealthStatus` in `common/` so both providers + future ones share the same shape.
- Registries (`agents/lipsync/core/registry.py`, `agents/voice/core/registry.py`) — orchestrator resolves a provider by name (`LIPSYNC_BACKEND`, `TTS_BACKEND`) without importing concrete classes.
- **SadTalker stub** — declares the 5 required checkpoints, resolves `SADTALKER_MODELS_ROOT` (or falls back to `LIPSYNC_MODELS_ROOT/sadtalker`), on-disk healthcheck, fail-fast `synthesize()` (token first, then assets, then `ProviderNotImplementedError`).
- **Piper stub** — declares the configured voice's `.onnx` + `.onnx.json`, resolves `PIPER_MODELS_ROOT` (or `TTS_MODELS_ROOT/piper`), on-disk healthcheck, fail-fast `synthesize()`.
- **MuseTalk + Wav2Lip placeholders** — implement the contract; report `not_implemented`; refuse to run.
- 23-test Phase 3A suite covering: healthcheck states, fail-fast token + asset checks, placeholders, registry resolution, and a subprocess-isolated check that no `torch` / `diffusers` / `transformers` / `sadtalker` / `musetalk` / `piper` imports leak in.

Explicitly **not** in Phase 3A:

- No model weights downloaded. All assets must be manually placed under `./models/` per `docs/runbooks/model-management.md`.
- No `torch` / `torchvision` / `torchaudio` / `diffusers` / `transformers` / SadTalker / MuseTalk / Wav2Lip / GFPGAN / Piper runtime dependencies.
- No real video / audio / face / lip-sync generation. `synthesize()` raises `ProviderNotImplementedError` even when the provider is fully configured.
- No external paid APIs.
- DAG handlers (Phase 2) are still no-ops; the providers exist alongside but are NOT wired into the DAG yet — that wiring is Phase 3B.

## Phase 2 scope (still active)

Implemented on top of Phase 1:

- Shared `common/` package — `JobStatus`, `StageStatus`, `StageName`, `ComplianceDecisionType`, `ArtifactRef`, `StageOutput`, `ComplianceTokenClaims`, `DagState`. Both backend and agents depend on this; agents no longer import backend types (DB access coupling is documented; see [`agents/orchestrator/README.md`](agents/orchestrator/README.md)).
- `StageRun` Postgres model recording every DAG-stage execution (`stage_runs` table).
- `DagRunner` (`agents/orchestrator/dag.py`) — hand-rolled state machine reading the canonical stage order from `pipelines/reel_default.yaml`.
- No-op handlers for every stage (`agents/{scriptwriter,voice,face,lipsync,editor,qc,publisher}/handler.py`).
- Compliance Officer:
  - `pre_lipsync_auth` — mints an HMAC-signed `compliance_token` carrying `synthetic_person_confirmed`, `consent_confirmed`, `watermark_required`, `c2pa_required`, `allowed_lipsync_backend`, `issued_at`, `expires_at`, `phase="phase2_noop"`.
  - `identity_guard` — no-op (real CLIP-NN check deferred to Phase 5).
  - `export_disclosure_validation` — no-op (real OCR + C2PA verify deferred to Phase 5).
- LipSync handler **refuses** to run without a valid `compliance_token`.
- `JobStatus` extended with `published`; a valid job transitions `pending_compliance → accepted → published`.
- Integration test (`tests/integration/test_phase2_noop_dag.py`) verifies the full path, all rejection paths, the token, and the metadata-only invariant.

Explicitly **not** in Phase 2:

- No model weights are downloaded.
- No GPU libraries (torch / diffusers / transformers / SadTalker / MuseTalk / Wav2Lip).
- No real video, audio, face, or lip-sync generation — all artifact references are stub MinIO URIs.
- No external paid APIs.
- No LangGraph — the DAG runner is a 200-line hand-rolled state machine. The handler interface is LangGraph-compatible; Phase 3+ can swap in `langgraph` if branching/retry/parallelism warrants the dep.
- Real SadTalker / MuseTalk / Wav2Lip integration is deferred to Phase 3 behind the existing `LipSyncProvider` adapter contract.

## License

TBD — to be selected at v1 release. Until then, all rights reserved by the project owner.
