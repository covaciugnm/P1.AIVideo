# API routes + providers — consolidated reference (Phase 21)

Single source of truth for **every HTTP route the backend exposes** and
**every provider (LLM / TTS / video / image) currently registered**.
Auto-generated from `/openapi.json` + `/api/v1/providers` on
2026-05-19; refresh when the catalog changes.

---

## 1. HTTP routes — `/api/v1/*` + `/healthz`

| Method | Path | Summary |
|---|---|---|
| `GET   ` | `/api/v1/artifact-types` | List Artifact Types |
| `GET   ` | `/api/v1/artifacts/{artifact_id}/content` | Get Artifact Content |
| `POST  ` | `/api/v1/audio/fit-check` | Audio Fit Check |
| `GET   ` | `/api/v1/characters` | List Characters |
| `POST  ` | `/api/v1/characters` | Create Character |
| `GET   ` | `/api/v1/characters/lookups` | Get Character Lookups |
| `GET   ` | `/api/v1/characters/available-voices` | List TTS voices not reserved by another active/editing character (Phase 23) |
| `GET   ` | `/api/v1/characters/{character_id}` | Get Character |
| `PUT   ` | `/api/v1/characters/{character_id}` | Update Character |
| `POST  ` | `/api/v1/characters/{character_id}/status` | Lifecycle transition editing/active/retired (Phase 23) |
| `DELETE` | `/api/v1/characters/{character_id}` | Delete Character |
| `GET   ` | `/api/v1/characters/{character_id}/images` | List Images |
| `POST  ` | `/api/v1/characters/{character_id}/images/generate` | Generate Image |
| `DELETE` | `/api/v1/characters/{character_id}/images/{image_id}` | Delete Image |
| `POST  ` | `/api/v1/characters/{character_id}/images/{image_id}/accept` | Accept Image |
| `POST  ` | `/api/v1/characters/{character_id}/images/{image_id}/archive` | Archive Image |
| `GET   ` | `/api/v1/characters/{character_id}/images/{image_id}/content` | Serve Image Content |
| `POST  ` | `/api/v1/characters/{character_id}/images/{image_id}/reject` | Reject Image |
| `POST  ` | `/api/v1/characters/{character_id}/images/{image_id}/set-main-reference` | Set Main Reference |
| `GET   ` | `/api/v1/characters/{character_id}/script-context` | Get Character Script Context |
| `GET   ` | `/api/v1/characters/{character_id}/videos` | List Character Videos |
| `GET   ` | `/api/v1/config/languages` | Get Languages Config |
| `GET   ` | `/api/v1/config/ui-options` | Get UI Options |
| `POST  ` | `/api/v1/export/finalize` | Export Finalize |
| `POST  ` | `/api/v1/jobs` | Create Job |
| `GET   ` | `/api/v1/jobs` | List Videos (legacy name: jobs) |
| `POST  ` | `/api/v1/jobs/from-inputs` | Create Video from inputs |
| `GET   ` | `/api/v1/jobs/{job_id}` | Get Video |
| `PATCH ` | `/api/v1/jobs/{job_id}` | Update Video |
| `DELETE` | `/api/v1/jobs/{job_id}` | Delete Video |
| `GET   ` | `/api/v1/jobs/{job_id}/artifacts` | Get Video Artifacts |
| `POST  ` | `/api/v1/jobs/{job_id}/cancel` | Cancel Video |
| `GET   ` | `/api/v1/jobs/{job_id}/compliance-events` | Get Compliance Events |
| `GET   ` | `/api/v1/jobs/{job_id}/final-export` | Get Final Export |
| `GET   ` | `/api/v1/jobs/{job_id}/progress` | Get Progress |
| `GET   ` | `/api/v1/jobs/{job_id}/qc-report` | Get QC Report |
| `POST  ` | `/api/v1/jobs/{job_id}/retry` | Retry Video |
| `GET   ` | `/api/v1/jobs/{job_id}/summary` | Get Full Summary |
| `GET   ` | `/api/v1/jobs/{job_id}/timeline` | Get Timeline |
| `GET   ` | `/api/v1/providers` | List Providers (all categories) |
| `GET   ` | `/api/v1/providers/audio-processors` | List Audio Processor Providers |
| `GET   ` | `/api/v1/providers/image-generators` | List Image Generator Providers |
| `GET   ` | `/api/v1/providers/image-processors` | List Image Processor Providers |
| `GET   ` | `/api/v1/providers/llm` | List LLM Providers |
| `GET   ` | `/api/v1/providers/tts` | List TTS Providers |
| `GET   ` | `/api/v1/providers/tts/{provider_id}/sample.wav` | Stream voice sample WAV (Phase 21) |
| `GET   ` | `/api/v1/providers/video-generators` | List Video Providers |
| `GET   ` | `/api/v1/providers/{category}/{provider_id}` | Get Provider Detail |
| `POST  ` | `/api/v1/providers/{category}/{provider_id}/health-check` | Health-check Provider |
| `POST  ` | `/api/v1/qc/inspect` | QC Inspect (one-off) |
| `POST  ` | `/api/v1/script/generate` | Script Generate (mode: spoken_script / image_description / scene_plan) |
| `GET   ` | `/api/v1/secrets` | List Secrets |
| `POST  ` | `/api/v1/secrets` | Upsert Secret |
| `PUT   ` | `/api/v1/secrets/{key_name}` | Update Secret |
| `DELETE` | `/api/v1/secrets/{key_name}` | Delete Secret |
| `POST  ` | `/api/v1/secrets/{key_name}/test` | Test Secret |
| `GET   ` | `/api/v1/settings/ui` | Get UI Settings |
| `PATCH ` | `/api/v1/settings/ui` | Patch UI Settings |
| `GET   ` | `/api/v1/stages` | List Stages |
| `GET   ` | `/api/v1/system/logs/backend` | Get Backend Logs (ring buffer) |
| `GET   ` | `/api/v1/system/status` | Get System Status |
| `GET   ` | `/api/v1/system/technical-architecture` | Get Technical Architecture (JSON) |
| `GET   ` | `/api/v1/system/technical-architecture.md` | Get Technical Architecture (Markdown) |
| `GET   ` | `/api/v1/system/wrappers` | Get GPU Wrapper Status |
| `POST  ` | `/api/v1/tts/generate` | TTS Generate (one-off preview) |
| `POST  ` | `/api/v1/uploads/audio` | Upload Audio |
| `POST  ` | `/api/v1/uploads/image` | Upload Image |
| `POST  ` | `/api/v1/uploads/text` | Upload Text |
| `POST  ` | `/api/v1/video/generate` | Video Generate (one-off lipsync) |
| `GET   ` | `/healthz` | Health check (root) |

Phase 21 additions:
- `GET /api/v1/providers/tts/{provider_id}/sample.wav` (voice preview)
- `POST /api/v1/script/generate` now accepts `mode` =
  `spoken_script` / `image_description` / `scene_plan`.

---

## 2. LLM providers

| Provider ID | Status | Gateway | Notes |
|---|---|---|---|
| `template` | ✅ available | local-deterministic | No network, no models — used as the fallback the UI defaults to. |
| `mock` | ✅ available | local-deterministic | Fixed output for tests. |
| `ollama_qwen3_5_9b-q4` | ✅ configured | Ollama daemon | Per-model row (Phase 19). Lower-VRAM (9B). |
| `ollama_qwen3_6_27b-q4` | ✅ configured | Ollama daemon | Per-model row (Phase 19). Best quality on this stack. **Default**. |
| `vllm` | ✅ configured | vLLM HTTP | Operator-deployed; no models bundled. |
| `anthropic` | ○ not_configured | Claude API | Set `ANTHROPIC_API_KEY`. |
| `openai` / `openai_compatible` | ○ not_configured | OpenAI / compat API | Set `OPENAI_API_KEY`. |
| `local_http` | ○ not_configured | Operator HTTP | Set `LOCAL_HTTP_LLM_BASE_URL`. |

Selectable via `provider_selection.script_provider_id`.
`/script/generate` knobs (env, all forwarded to Ollama):
`OLLAMA_TEMPERATURE` (0.7), `OLLAMA_TOP_P` (0.9), `OLLAMA_TOP_K` (20),
`OLLAMA_REPEAT_PENALTY` (1.05), `OLLAMA_NUM_CTX` (8192),
`OLLAMA_NUM_PREDICT` (4096), `OLLAMA_STOP` (`<|im_end|>;;<|endoftext|>`).

---

## 3. TTS providers

| Provider ID | Status | Gender | Language | Sample URL |
|---|---|---|---|---|
| `piper` | ○ not_configured | female | en | — |
| `f5tts_ro_ro_default` | ✅ configured | neutral | ro | `/api/v1/providers/tts/f5tts_ro_ro_default/sample.wav` |
| `f5tts_ro_ro_barbat_1_linistit` | ✅ configured | male | ro | `…/f5tts_ro_ro_barbat_1_linistit/sample.wav` (fine-tuned 95k steps) |
| `f5tts_ro_ro_barbat_2_prezentator` | ✅ configured | male | ro | `…/f5tts_ro_ro_barbat_2_prezentator/sample.wav` (fine-tuned 125k steps) |
| `f5tts_ro_ro_barbat_3_costel` | ✅ configured | male | ro | `…/f5tts_ro_ro_barbat_3_costel/sample.wav` |
| `f5tts_ro_ro_barbat_4_dorel` | ✅ configured | male | ro | `…/f5tts_ro_ro_barbat_4_dorel/sample.wav` |
| `f5tts_ro_ro_barbat_5_georgel` | ✅ configured | male | ro | `…/f5tts_ro_ro_barbat_5_georgel/sample.wav` |
| `f5tts_ro_ro_femeie_1_lacramioara` | ✅ configured | female | ro | `…/f5tts_ro_ro_femeie_1_lacramioara/sample.wav` |
| `f5tts_ro_ro_femeie_2_marioara` | ✅ configured | female | ro | `…/f5tts_ro_ro_femeie_2_marioara/sample.wav` |
| `coqui_tts` / `xtts` / `styletts` | ✗ not_implemented | — | — | research-only |
| `elevenlabs_compatible` / `openai_compatible_tts` / `local_http_tts` | ✗ not_implemented | — | — | external/operator |

Catalog source: `models/tts/f5tts-ro/voices.yaml`. Add a voice by
dropping `voices/<id>/ref_audio.wav` + `ref_text.txt` (+ optional
`model.pt`) and appending a YAML entry.

UI filtering: each TTS entry is hidden unless its language matches the
selected video language AND its gender matches the character's gender
(neutral voices always shown).

---

## 4. Video generator providers (lipsync + text-to-video)

| Provider ID | Status | GPU | Use |
|---|---|---|---|
| `sadtalker` | ✅ available | yes | Default lipsync (Phase 7B–11H). News-presenter presenter segments. |
| `wav2lip` | ✅ configured | yes | Lightweight lipsync fallback. |
| `musetalk` / `liveportrait` / `echomimic` / `hallo` | ✅ configured | yes | Phase 12Y HTTP wrappers; alternative lipsync families. |
| `svd` / `animatediff` / `ltx_video` / `hunyuan_video` / `mochi` | ✅ configured | yes | Text-to-video / image-to-video stubs (Phase 21+ pending wiring). |
| `local_http_video` / `external_video_api` | ✗ not_implemented | — | Operator endpoint stubs. |

---

## 5. Image generator providers (Phase 12 — Characters + Phase 21 — scenes)

| Provider ID | Status | GPU | Use |
|---|---|---|---|
| `flux_local` | ✅ configured | yes | **FLUX.1-schnell** wrapper (`model-flux`). Default for scenes_only / news_presenter B-roll AND talking-head character portrait. |
| `sd35_local` / `sdxl_local` | ✅ configured | yes | Alternative diffusers wrappers. |
| `a1111_local` / `comfyui_local` | ✅ configured | yes | Operator-runtime SD WebUI / ComfyUI. |
| `mock` | ✅ available | no | Deterministic placeholder for CI. |
| `fal_api` / `flux_bfl_api` / `ideogram_api` / `midjourney_unofficial` / `openai_dalle3` / `recraft_api` / `replicate_api` / `stability_api` / `together_api` / `vertex_imagen3` | ○ not_configured | — | External APIs — set the relevant secret in `/secrets`. |

---

## 6. Job types (Phase 21)

| `job_type` | Pipeline (stages) | What it makes | Required inputs |
|---|---|---|---|
| `talking_head` (default) | `policy_gate → scriptwriter → voice → face → identity_guard → pre_lipsync_auth → lipsync → editor → qc → export_disclosure_validation → publisher` (11 stages) | Single character portrait + lipsynced narration over the full video. | character + image_artifact_id (or face_mode=provided_image), script_text |
| `scenes_only` | `policy_gate → scriptwriter → scene_composer → qc → export_disclosure_validation → publisher` (6 stages) | Voice-over B-roll scenes (no character on screen); each scene is a FLUX image + Ken-Burns + per-scene TTS, ffmpeg-concatenated. | scene_plan with all `kind="broll"`; no character needed |
| `news_presenter` | `policy_gate → scriptwriter → face → identity_guard → pre_lipsync_auth → scene_composer → qc → export_disclosure_validation → publisher` (9 stages) | Hybrid: presenter (lipsync on character portrait) **interleaved** with B-roll scene clips. | character + scene_plan with at least one `kind="presenter"` |

---

## 7. Subtitle pipeline (Phase 21 burn-in fix)

- **`subtitle_enabled` + `subtitle_languages`**: at job-create time the
  backend writes one SRT/VTT per language under `artifacts` (cue
  timing is currently approximate).
- **`subtitle_burn_in`**: editor stage re-encodes the final reel with
  ffmpeg `subtitles=…:force_style='FontName=DejaVu Sans,Fontsize=22,…'`
  so captions are baked into the pixels (Phase 21).
- **`transcript_language`**: optional override — picks which sidecar
  SRT is burned in (e.g. RO voice + EN captions).

---

## 7b. Character lifecycle + TTS exclusivity (Phase 23)

A character moves through three states (legacy `inactive`/`draft` still
resolve labels for historical rows):

| State | Photos/videos? | Reserves its TTS voice? | Identity + voice editable? |
|---|---|---|---|
| `editing` | no (must activate first) | **yes** | yes |
| `active` | **yes** | **yes** | **no** (face, date_of_birth, gender, voice are locked) |
| `retired` | no | **no** — voice is released for reuse | re-open via → `editing` |

Rules enforced server-side (HTTP **409** on violation):

- **Voice exclusivity** — a TTS `provider_id` reserved by an `active`/`editing`
  character is rejected on create/update for any other character, and is
  filtered out of `GET /characters/available-voices` for them.
  `GET /characters/available-voices?character_id=<id>` keeps the owner's
  own voice in the list.
- **Immutability** — while `active`, `identity.date_of_birth`,
  `identity.gender` and the TTS voice cannot change; move to `editing` first.
- **Generation gate** — `retired` (and legacy `inactive`) block both
  `POST /characters/{id}/images/generate` and `POST /jobs` (when the job
  is bound to that character).
- **Activation requires** a `main_reference_image_id` (an accepted face)
  **and** an assigned voice.

Valid transitions: `editing↔active`, `active→retired`, `editing→retired`,
`retired→editing` (voice must still be free), `inactive→editing` (legacy revive).

---

## 8. End-to-end smoke checklist

```sh
# 1. List all routes
curl -s http://localhost:8001/openapi.json | jq '.paths | keys[]' | grep '^"/api/v1'

# 2. List all providers
curl -s http://localhost:8001/api/v1/providers | jq

# 3. List TTS voices for a Romanian female character
curl -s http://localhost:8001/api/v1/providers | jq '.tts[] | select(.language=="ro" and .voice_gender=="female")'

# 4. Preview a voice
curl -s http://localhost:8001/api/v1/providers/tts/f5tts_ro_ro_femeie_2_marioara/sample.wav -o sample.wav

# 5. Trigger an LLM scene plan
curl -s -X POST http://localhost:8001/api/v1/script/generate -H 'content-type: application/json' \
  -d '{"brief":"Sleep tips","target_duration_seconds":20,"language":"ro","provider_id":"ollama","model":"qwen3.6:27b-q4","mode":"scene_plan","job_type_hint":"news_presenter","character_gender":"female"}'
```
