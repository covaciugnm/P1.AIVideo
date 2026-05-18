// Phase 11A — English Help corpus. 30 required topics + a couple of
// cross-references kept from the earlier corpus.
//
// Every topic has ``id``, ``title``, ``summary``, ``body`` (rich blocks)
// and optional ``related``. The HelpOverlay reads from this file when
// the UI language is English, and from ``./ro.ts`` for Romanian. Missing
// topics fall back to the English version — the runtime never crashes.

import type { HelpBlock } from "../types";

export interface HelpTopic {
  readonly id: string;
  readonly section: string;
  readonly title: string;
  readonly summary: string;
  readonly body: readonly HelpBlock[];
  readonly related?: readonly string[];
}

const p = (text: string): HelpBlock => ({ type: "p", text });
const h = (level: 2 | 3 | 4, text: string): HelpBlock => ({ type: "h", level, text });
const kv = (
  rows: readonly (readonly [string, string])[],
  caption?: string,
): HelpBlock => ({ type: "kv", caption, rows });
const code = (text: string, caption?: string, lang?: string): HelpBlock => ({
  type: "code",
  text,
  caption,
  lang,
});
const callout = (
  tone: "info" | "warn" | "danger" | "success",
  text: string,
  title?: string,
): HelpBlock => ({ type: "callout", tone, text, title });
const list = (items: readonly string[], ordered = false): HelpBlock => ({
  type: "list",
  items,
  ordered,
});

export const HELP_TOPICS_EN: Readonly<Record<string, HelpTopic>> = {
  dashboard: {
    id: "dashboard",
    section: "Dashboard",
    title: "Dashboard",
    summary: "Stack health, latest jobs, and quick links — the landing screen.",
    body: [
      p("The Dashboard summarises stack health and links to the main flows. The top-right Backend status badge polls /healthz so you know the API is alive."),
      p("The recent-jobs table is a thin projection of GET /api/v1/jobs sorted by created_at. Click any row to drill into Job Detail."),
      list([
        "Quick links jump to Jobs / New job / Uploads / Settings.",
        "Activity sidebar is collapsible — collapse it for screen real estate.",
        "Press ? at any time to open this help overlay.",
      ]),
    ],
    related: ["jobs-list", "create-job", "settings"],
  },
  "jobs-list": {
    id: "jobs-list",
    section: "Jobs",
    title: "Jobs list",
    summary: "Browse every job, filter by status, drill into detail.",
    body: [
      p("/jobs is the operational table-of-contents. Rows show id, brief, current stage, status, progress, and creation time."),
      kv([
        ["Brief", "First 60 chars of the operator brief."],
        ["Status", "pending_compliance / accepted / published / rejected / failed."],
        ["Stage", "Currently running stage, or last completed for terminal jobs."],
        ["Progress", "Percentage of stages completed."],
        ["Language", "Phase 11A — video_language of the job (ro / en)."],
      ]),
      p("The status filter trims the table without re-fetching everything."),
    ],
    related: ["create-job", "job-detail", "recovery-controls"],
  },
  "create-job": {
    id: "create-job",
    section: "Jobs",
    title: "Create job",
    summary: "Multi-tab wizard for a new reel: brief → providers → language → compliance.",
    body: [
      p("Each tab validates locally before letting you proceed; nothing reaches the backend until you submit."),
      kv([
        ["Brief", "Free-text description + target duration. The scriptwriter uses this as the prompt."],
        ["Voice", "Pick TTS mode (synthesise) or provided audio (upload first, then link)."],
        ["Providers", "Override deploy defaults — script / voice / video provider ids. Inherit-default is fine."],
        ["Language + subtitles", "Phase 11A — pick video language; optionally enable sidecar SRT/VTT subtitles."],
        ["Compliance", "Two mandatory attestations. Submit stays disabled until both are ticked."],
      ]),
      p("Image / audio refs are sent as full ref objects (type=local_path, path, mime_type, checksum). The form builds those from the artifact you picked under Uploads."),
    ],
    related: ["provider-selection", "video-language", "subtitles", "uploads"],
  },
  "provider-selection": {
    id: "provider-selection",
    section: "Providers",
    title: "Provider selection",
    summary: "Per-job override for script / TTS / video / audio-processor / image-processor.",
    body: [
      p("provider_selection is a JSON dict stored on the Job row. Each field is optional; missing fields inherit the deploy default."),
      kv([
        ["script_provider_id", "template (deterministic) | ollama (local LLM)."],
        ["tts_provider_id", "piper | f5tts_ro | external."],
        ["video_provider_id", "sadtalker | musetalk | wav2lip | liveportrait."],
        ["audio_processor_id", "Usually ffmpeg_convert."],
        ["image_processor_id", "Usually stdlib_image_validation."],
      ]),
      callout("info", "Custom providers can be registered in Settings → Custom providers (localStorage; backend persistence lands later)."),
    ],
    related: ["script-generation", "tts-generation", "sadtalker-video", "custom-providers"],
  },
  "script-generation": {
    id: "script-generation",
    section: "Generation",
    title: "Script generation",
    summary: "Brief → structured script. Template is deterministic; Ollama is a local LLM.",
    body: [
      p("POST /api/v1/script/generate runs the chosen provider. Template returns a deterministic 3-part script (hook / body / cta) and is always available."),
      p("Ollama calls a local daemon (default http://localhost:11434). It is gated behind SCRIPTWRITER_ENABLE_NETWORK_CALLS=true so a fresh install never makes outbound requests."),
      kv([
        ["script_provider_disabled", "Network calls disabled — flip the env var."],
        ["script_model_missing", "Run `ollama pull <model>` and retry."],
        ["script_provider_unreachable", "Daemon down or OLLAMA_BASE_URL wrong."],
        ["script_generation_failed", "Daemon responded but response failed validation."],
      ]),
    ],
    related: ["ollama", "create-job"],
  },
  "tts-generation": {
    id: "tts-generation",
    section: "Generation",
    title: "TTS generation",
    summary: "Text → audio. Piper for English (and others), F5TTS-Ro for Romanian.",
    body: [
      p("POST /api/v1/tts/generate runs the chosen TTS backend and registers an audio artifact (or returns a categorised 503 if a gate fails)."),
      kv([
        ["tts_runtime_missing", "piper-tts / f5-tts not installed in the image."],
        ["tts_assets_missing", "Voice / model files missing on disk."],
        ["tts_generation_failed", "Synthesis ran but the WAV failed validation."],
        ["tts_provider_not_configured", "Env var (PIPER_MODELS_ROOT, F5TTS_RO_BASE_URL) not set."],
        ["tts_provider_not_implemented", "Provider is a placeholder."],
      ]),
    ],
    related: ["piper", "f5tts-ro", "create-job"],
  },
  "f5tts-ro": {
    id: "f5tts-ro",
    section: "Providers",
    title: "F5TTS-Ro (Romanian)",
    summary: "Real Romanian TTS using cdorob/f5-tts-romanian on an opt-in GPU/CPU wrapper.",
    body: [
      p("F5TTS-Ro is an opt-in Docker service (profile=tts-ro) that wraps upstream F5-TTS with the cdorob/f5-tts-romanian Romanian fine-tune. The backend light image stays torch-free; the wrapper does the heavy ML work."),
      h(3, "Model: cdorob/f5-tts-romanian"),
      kv([
        ["HF repo", "huggingface.co/cdorob/f5-tts-romanian"],
        ["License", "MIT"],
        ["Base model", "F5TTS_v1_Base (upstream SWivid/F5-TTS)"],
        ["Training data", "Common Voice 17 RO (35k samples) + datadriven-company/TTS-Romanian (50k samples), ~173h total"],
        ["Files", "model_last.pt (5.4 GB) + vocab.txt (~14 KB)"],
        ["Tokenizer", "character-based"],
      ]),
      h(3, "Required operator-supplied assets"),
      list([
        "models/tts/f5tts-ro/model/model_last.pt — the cdorob checkpoint (download via huggingface_hub, see runbook).",
        "models/tts/f5tts-ro/model/vocab.txt — ships in the same HF repo.",
        "models/tts/f5tts-ro/reference/voice.wav — clean Romanian reference WAV, 3–15 seconds, single speaker.",
        "models/tts/f5tts-ro/reference/reference.txt — exact transcript of the reference WAV (F5-TTS uses it for voice cloning alignment).",
      ]),
      h(3, "Setup"),
      code("# 1. download the model (~5.4 GB, MIT license, no auth)\nhuggingface-cli download cdorob/f5-tts-romanian --local-dir models/tts/f5tts-ro/model\n\n# 2. place a synthetic Romanian reference WAV + matching transcript\nls models/tts/f5tts-ro/reference/voice.wav models/tts/f5tts-ro/reference/reference.txt\n\n# 3. build + start the wrapper (heavy ML layer is opt-in via INSTALL_F5TTS=true, default true)\nmake docker-tts-ro-build\nmake docker-tts-ro-up\n\n# 4. tell the backend where the wrapper lives\nexport F5TTS_RO_BASE_URL=http://aivideo-model-tts-ro-1:8080", "Operator-supplied assets + service start. No auto-download except via huggingface_hub when explicitly invoked.", "bash"),
      callout("info", "When to pick F5TTS-Ro vs Piper: F5TTS-Ro produces higher-quality Romanian audio (voice-cloned from your reference WAV) but costs ~80–120 seconds per request on CPU (faster on GPU). Piper is ~1 second per request and is the right default for short scripts or low-latency development.", "Performance trade-off"),
      callout("warn", "The wrapper image bundles torch + f5-tts (~2 GB image growth). Build with --build-arg INSTALL_F5TTS=false to keep an honest /health-only wrapper that always reports runtime_missing.", "Image size"),
    ],
    related: ["tts-generation", "provider-selection", "model-assets", "piper"],
  },
  piper: {
    id: "piper",
    section: "Providers",
    title: "Piper (local TTS)",
    summary: "Default English TTS. CPU-friendly, fast, no network.",
    body: [
      p("Piper is the default TTS engine. Install it by rebuilding the backend with INSTALL_PIPER=true, then place voice files (.onnx + .onnx.json) under PIPER_MODELS_ROOT."),
      code("INSTALL_PIPER=true make docker-light-build\nmake docker-light-up\n# Drop voices under models/tts/piper/<voice>/<voice>.onnx + .onnx.json", undefined, "bash"),
    ],
    related: ["tts-generation", "model-assets"],
  },
  ollama: {
    id: "ollama",
    section: "Providers",
    title: "Ollama (script LLM)",
    summary: "External local LLM. Not installed in the backend container — operator runs the Ollama daemon separately.",
    body: [
      p("Ollama is an external local LLM service. It is not installed inside the backend container. To use it, install/run Ollama separately, pull the configured model, set OLLAMA_BASE_URL, and enable SCRIPTWRITER_ENABLE_NETWORK_CALLS=true. If unavailable, use the Template provider."),
      h(3, "Status semantics"),
      kv([
        ["Installed", "No — Ollama is an external host/container service."],
        ["Configured", "Partially — through OLLAMA_BASE_URL (default http://host.docker.internal:11434 inside compose, http://localhost:11434 from the host shell)."],
        ["Functional", "Only if SCRIPTWRITER_ENABLE_NETWORK_CALLS=true AND the daemon is reachable AND the configured model is pulled."],
        ["Fallback", "If Ollama is disabled or unreachable, the application uses the Template provider (deterministic / static script)."],
      ]),
      h(3, "Setup"),
      code("# 1. Install Ollama on host (or run in a sibling container)\ncurl -fsSL https://ollama.com/install.sh | sh\nollama serve\n\n# 2. Pull the model (operator-explicit — never auto-pulled)\nollama pull qwen2.5:7b\n\n# 3. Tell the backend where the daemon lives + flip the network gate\nexport OLLAMA_BASE_URL=http://host.docker.internal:11434\nexport OLLAMA_MODEL=qwen2.5:7b\nexport SCRIPTWRITER_ENABLE_NETWORK_CALLS=true\n\n# 4. Restart backend + verify\ndocker compose -f docker/compose.dev.yml up -d backend\ncurl -fsS http://localhost:8001/api/v1/providers/llm | jq '.[] | select(.provider_id==\"ollama\")'", "Bring an external Ollama daemon online and connect the backend to it. Replace qwen2.5:7b with whatever model you prefer (qwen3.6 is the project default).", "bash"),
      h(3, "Error codes"),
      kv([
        ["script_provider_disabled", "SCRIPTWRITER_ENABLE_NETWORK_CALLS=false. Toggle on and restart."],
        ["script_provider_unreachable", "OLLAMA_BASE_URL points nowhere. Check `ollama serve` is up and reachable from the backend container."],
        ["script_model_missing", "Daemon is reachable but the configured model isn't pulled. Run `ollama pull <model>` on the Ollama host."],
        ["script_generation_failed", "Daemon responded but the body was malformed. Check daemon logs."],
      ]),
      callout("warn", "The application NEVER runs `ollama pull` automatically. The Makefile exposes `make ollama-status` / `make ollama-models` / `make ollama-smoke` for diagnostics; no target pulls models without operator confirmation.", "No auto-pull"),
    ],
    related: ["script-generation", "errors-glossary", "provider-selection"],
  },
  "sadtalker-video": {
    id: "sadtalker-video",
    section: "Providers",
    title: "SadTalker video",
    summary: "Real lip-synced MP4 generation on the GPU wrapper service.",
    body: [
      p("SadTalker is the v1 default video provider. It runs in a dedicated Docker service (profile=sadtalker, port 8062). The light backend proxies /api/v1/video/generate to the wrapper over HTTP."),
      h(3, "Requirements"),
      list([
        "NVIDIA driver + NVIDIA Container Toolkit on the host.",
        "GPU with ≥6 GB VRAM.",
        "Five weight files under models/lipsync/sadtalker/{checkpoints,gfpgan}/ (~2 GB total).",
        "SADTALKER_BASE_URL=http://aivideo-model-sadtalker-1:8080 on the backend.",
      ]),
      callout("info", "Phase Demo-RO-1 patches the cross-uid permission issue: backend + orchestrator chmod 0o777 the per-job artifacts subdir so the wrapper (uid 10002) can move the MP4 in.", "Permissions automatic"),
      h(3, "Portrait requirements"),
      p("SadTalker runs a face detector + landmark extractor on the source image before it can animate a talking head. The detector is strict; a recognisable front-facing portrait is required."),
      list([
        "One visible human face — group photos, full bodies, or empty backgrounds fail.",
        "Front-facing or near-frontal — strict profile shots cannot be cropped.",
        "Good lighting — silhouettes, very dark or very washed-out images fail.",
        "No strong occlusion — sunglasses, masks, hands across the face, heavy hair across the face all hurt landmark detection.",
        "Minimum size 256×256, recommended ≥512×512 (the suitability precheck refuses anything smaller).",
        "PNG / JPEG / WebP, decoded by the wrapper's OpenCV.",
        "Synthetic person only — operator consent + synthetic_person flags are mandatory by compliance policy.",
      ]),
      h(3, "Categorised failure codes"),
      kv([
        ["video_face_landmark_missing", "SadTalker's cropper did not find a face in the source image. Upload a clearer front-facing portrait and retry. The job stays in 'rejected' so PATCH + retry is supported."],
        ["video_face_image_too_small", "Image is <256×256. The backend's suitability precheck refuses it before SadTalker is invoked."],
        ["video_assets_missing", "One of the five required weight files is not under SADTALKER_MODELS_ROOT."],
        ["video_gpu_missing", "torch can't see a CUDA device. Check `nvidia-smi` and the container's --gpus all flag."],
        ["video_runtime_missing", "The wrapper image is missing torch / opencv / SadTalker source — operator must rebuild."],
        ["video_generation_failed", "Catch-all: SadTalker exited non-zero with no recognised signature. Check the diagnostics panel for the subprocess tail."],
      ]),
    ],
    related: ["gpu-runtime", "model-assets", "video-language", "image-upload", "failed-job-recovery"],
  },
  subtitles: {
    id: "subtitles",
    section: "Media",
    title: "Subtitles",
    summary: "Sidecar SRT / VTT generated from the script. Burn-in not implemented.",
    body: [
      p("Phase 11A adds opt-in sidecar subtitle generation. Enable `Generate subtitles` on the Create Job form and pick one or more languages; the backend writes one .srt or .vtt per language under /storage/artifacts/subtitles/<job_id>/."),
      kv([
        ["subtitle_enabled", "Master toggle, persisted on the Job row."],
        ["subtitle_languages", "List of language codes. Auto-defaults to [video_language] when on but empty."],
        ["subtitle_format", "srt or vtt."],
        ["subtitle_burn_in", "Captured on the Job row; burn-in execution NOT implemented — files stay sidecar."],
      ]),
      callout("warn", "Cues are spread evenly across target_duration_seconds. Metadata says alignment=approximate / real_timing=false. Real forced alignment is future work.", "Approximate timing"),
    ],
    related: ["video-language", "artifacts", "create-job"],
  },
  "video-language": {
    id: "video-language",
    section: "Media",
    title: "Video language",
    summary: "Spoken language of the reel. Persisted on the Job; affects subtitle defaults.",
    body: [
      p("Pick the spoken language under `Language and subtitles` on Create Job. Today ro/en are first-class; other codes fail schema validation."),
      list([
        "Romanian (ro): pair with F5TTS-Ro for synthesised voice. Provided WAV / MP3 also works.",
        "English (en): pair with Piper.",
      ]),
      p("video_language surfaces on the Job summary list, on Job Detail, and in the final_export metadata."),
    ],
    related: ["subtitles", "f5tts-ro", "piper", "settings"],
  },
  uploads: {
    id: "uploads",
    section: "Uploads",
    title: "Uploads",
    summary: "Drop text, audio, or images. Each one becomes a reusable artifact ref.",
    body: [
      p("Uploads are first-class artifacts — they get a sha256, a stable id, and live under the artifacts_data named volume just like generated outputs. Multiple jobs can reference the same uploaded ref."),
      kv([
        ["Text", "Plain text (UTF-8). Used as a script override or upload sidecar."],
        ["Audio", "audio/wav (PCM). MP3 / M4A auto-converted via ffmpeg server-side."],
        ["Image", "image/png, image/jpeg. Minimum 256×256 for SadTalker face detection; 1024×1024 ideal."],
      ]),
    ],
    related: ["audio-upload", "image-upload"],
  },
  "audio-upload": {
    id: "audio-upload",
    section: "Uploads",
    title: "Audio upload",
    summary: "WAV mandatory, MP3 / M4A auto-converted server-side via ffmpeg.",
    body: [
      kv([
        ["Native format", "audio/wav, PCM, 16 / 22.05 / 44.1 / 48 kHz, mono or stereo."],
        ["Auto-conversion", "audio/mpeg, audio/mp4 routed through ffmpeg → mono WAV at the original sample rate."],
        ["Min duration", "1 s (validated by audio_validation)."],
        ["Max duration", "AUDIO_MAX_DURATION_SECONDS (default 600 s)."],
      ]),
      callout("warn", "Make sure your curl sends the right MIME (`-F 'file=@x.wav;type=audio/wav'`) — application/octet-stream is rejected.", "MIME hints"),
    ],
    related: ["uploads", "create-job"],
  },
  "image-upload": {
    id: "image-upload",
    section: "Uploads",
    title: "Image upload",
    summary: "PNG / JPEG portraits. Minimum dimensions matter for face detection.",
    body: [
      kv([
        ["Allowed MIME", "image/png, image/jpeg."],
        ["Min dimensions", "256×256 for SadTalker face detection; ideal 1024×1024 portrait, face centered."],
        ["Max upload size", "UPLOAD_IMAGE_MAX_BYTES (default 20 MB)."],
      ]),
      callout("info", "thispersondoesnotexist.com produces CC0 AI faces that pass synthetic-only attestation.", "Synthetic-person sources"),
    ],
    related: ["uploads", "create-job"],
  },
  "job-detail": {
    id: "job-detail",
    section: "Jobs",
    title: "Job detail",
    summary: "Everything about one job: timeline, artifacts, compliance, QC, export, recovery.",
    body: [
      p("The Job Detail page is the single source of truth for one reel. It is composed of stacked cards, each safe to refresh independently."),
      kv([
        ["Header", "Brief, status chip, target duration, voice / face mode, edit / cancel / retry buttons."],
        ["Stage timeline", "All 10 DAG stages with their status, duration, and rejection reason if any."],
        ["Artifacts table", "Every artifact registered against the job, with type / size / duration / dims / download link."],
        ["Video / audio preview", "Inline <video> / <audio> for binary artifacts."],
        ["Compliance events", "Every accept / reject with timestamp + reason."],
        ["QC report", "Lip-sync confidence, watermark presence, AI disclosure status."],
        ["Final export card", "Published vs blocked, AI disclosure metadata, C2PA signing status."],
        ["Recovery controls", "Reset, retry from stage, or cancel."],
      ]),
    ],
    related: ["artifacts", "qc-report", "final-export", "recovery-controls"],
  },
  artifacts: {
    id: "artifacts",
    section: "Jobs",
    title: "Artifacts",
    summary: "Every output a stage produces is a typed artifact with sha256.",
    body: [
      kv([
        ["script", "JSON. Structured script (hook / body / cta / language)."],
        ["audio", "WAV file on disk."],
        ["image", "PNG / JPEG on disk."],
        ["video", "MP4 on disk."],
        ["subtitle", "SRT or VTT on disk. metadata_summary carries language_code + format."],
        ["edit_plan / metadata / qc_report / final_export", "Inline JSON."],
      ]),
      p("Binary artifacts are addressable via GET /api/v1/artifacts/<id>/content. Add ?download=true to get an attachment header."),
    ],
    related: ["real-vs-metadata", "subtitles"],
  },
  "real-vs-metadata": {
    id: "real-vs-metadata",
    section: "Jobs",
    title: "Real vs metadata",
    summary: "Some artifacts contain real bytes; others are placeholders for tests.",
    body: [
      p("Phase 1–6 demos produced metadata-only artifacts: a checksum + size, but the bytes were stub placeholders. Phase 10B+ produces real MP4s when the SadTalker wrapper is up."),
      list([
        "Real MP4: metadata_summary.phase=phase10b_sadtalker_via_wrapper, size in hundreds of KB.",
        "Stub MP4: sub-200 byte file, metadata_summary.phase=phase2_noop.",
        "The Artifact table always shows the byte count — 376 KB is real; 64 bytes is a placeholder.",
      ]),
    ],
    related: ["artifacts", "sadtalker-video"],
  },
  "qc-report": {
    id: "qc-report",
    section: "Jobs",
    title: "QC report",
    summary: "Lip-sync confidence + watermark + AI-disclosure check.",
    body: [
      p("The QC stage produces a JSON report scoring the reel against three checks. The Job Detail surfaces it as a card with a colored badge (pass / warn / fail)."),
      kv([
        ["lipsync_confidence", "0.0–1.0 score. Threshold around 0.7 today."],
        ["watermark_present", "boolean — overlay detected?"],
        ["disclosure_present", "boolean — AI-disclosure metadata present?"],
        ["decision", "pass | warn | fail."],
      ]),
      callout("info", "POST /api/v1/qc/inspect can re-run QC against an existing video artifact without re-running the whole DAG.", "Re-running QC"),
    ],
    related: ["job-detail", "final-export", "errors-glossary"],
  },
  "final-export": {
    id: "final-export",
    section: "Jobs",
    title: "Final export",
    summary: "Publisher bundle. Embeds AI disclosure, signs with C2PA when required.",
    body: [
      p("The publisher stage produces a final_export artifact summarising the published reel — output URI, size, sha256, watermark + C2PA status, and the AI disclosure metadata."),
      kv([
        ["status", "published | blocked | skipped."],
        ["disclosure_status", "embedded | missing | pending."],
        ["watermark_required / c2pa_required", "Echo of the operator's attestations."],
        ["export_uri", "Final on-disk URI."],
      ]),
      p("POST /api/v1/export/finalize can re-run the publisher bundle for an existing video artifact."),
    ],
    related: ["qc-report", "subtitles", "artifacts"],
  },
  "recovery-controls": {
    id: "recovery-controls",
    section: "Jobs",
    title: "Recovery controls",
    summary: "Retry, reset, cancel — without losing earlier artifacts.",
    body: [
      kv([
        ["Retry from stage…", "Pick the earliest stage to redo. Earlier artifacts stay attached."],
        ["Reset to compliance", "Sets status back to pending_compliance, drops every stage run. Inputs kept."],
        ["Cancel", "Terminal — sets status=failed with reason=operator_cancelled."],
      ]),
      callout("warn", "Reset / retry never delete artifacts off disk — they only un-link them from the active stage_run."),
    ],
    related: ["job-detail", "errors-glossary", "edit-job", "retry-job", "failed-job-recovery"],
  },
  "edit-job": {
    id: "edit-job",
    section: "Jobs",
    title: "Edit an existing job",
    summary: "Change brief, providers, script, language or subtitles before re-running the pipeline.",
    body: [
      p("The Edit page (link in the Jobs list and on the Job Detail header) lets you fix metadata on an existing job without creating a new one. Phase 11B widens the editable surface so rejected / failed jobs can be repaired."),
      kv([
        ["Brief / target duration", "Always editable until the job is published."],
        ["Script text", "Editable while the job is pending_compliance, rejected or failed."],
        ["Voice / face mode", "Same as script text — switch to ``provided_audio`` if TTS is broken in your env."],
        ["Provider selection", "Edit per category (script / TTS / video / audio / image). Empty means inherit deploy default."],
        ["Language + subtitles", "Edit video_language, subtitle_enabled, languages list, format, burn-in."],
        ["Watermark / C2PA flags", "Compliance-bound — must stay true."],
      ]),
      callout("info", "Editing a rejected / failed job does NOT auto-retry it. After saving, click Retry on the same page (or on Job Detail). The worker picks up the new metadata on its next pass."),
      callout("warn", "Custom_future_* providers (e.g. ``custom_future_tts``) are metadata-only placeholders. If a job rejects with ``tts_provider_not_configured``, switch to a wired provider (``piper`` or ``f5tts_ro``) and retry."),
    ],
    related: ["retry-job", "failed-job-recovery", "provider-selection", "job-detail", "create-job"],
  },
  "retry-job": {
    id: "retry-job",
    section: "Jobs",
    title: "Retry after editing",
    summary: "Re-queue a failed / rejected job so the worker re-runs the DAG with patched metadata.",
    body: [
      p("Retry is enabled when a job is in ``rejected`` or ``failed`` status. POST /api/v1/jobs/{id}/retry flips the status back to pending_compliance, clears the previous rejection reason, and the orchestrator worker picks the row up on the next poll cycle."),
      list([
        "Stage history is preserved — old stage_run rows stay for audit.",
        "retry_count and retry_requested_at land in recovery_metadata.",
        "Edit your provider / brief / script first, then click Retry. The new pass uses the patched values.",
      ]),
      callout("warn", "If you click Retry without fixing the root cause (e.g. still pointing at ``custom_future_tts``), the new pass will reject for the same reason."),
    ],
    related: ["edit-job", "failed-job-recovery", "recovery-controls"],
  },
  "failed-job-recovery": {
    id: "failed-job-recovery",
    section: "Jobs",
    title: "Recover a failed / rejected job",
    summary: "End-to-end recipe: diagnose the rejection reason, edit the offending field, retry.",
    body: [
      p("When a job reaches ``rejected`` or ``failed``, the Job Detail page surfaces the rejection_reason and links to the timeline so you can see which stage failed."),
      list([
        "Open the Job Detail page and read rejection_reason (e.g. ``tts_provider_not_configured: only 'piper' is wired``).",
        "Click Edit job. The form preloads the current provider selection, brief, script, language.",
        "Change the failing field — e.g. tts_provider_id from ``custom_future_tts`` to ``piper``.",
        "Save changes — the dashboard confirms ``Changes saved``.",
        "Click Retry after editing (or use the Recovery controls section on Job Detail). The worker re-runs the DAG.",
      ]),
      callout("info", "Use ``voice_mode=provided_audio`` plus a pre-uploaded audio artifact if you want to skip TTS entirely on a recovery pass."),
    ],
    related: ["edit-job", "retry-job", "errors-glossary"],
  },
  settings: {
    id: "settings",
    section: "Settings",
    title: "Settings",
    summary: "Deploy-level defaults, custom providers, UI preferences.",
    body: [
      kv([
        ["Backend API URL", "Where the dashboard talks to. Useful for remote backends."],
        ["Interface language", "ro / en. Persists in the operator_settings DB row + localStorage."],
        ["Default video language", "Used as the seed value when creating new jobs."],
        ["Polling interval", "How often the dashboard re-fetches /jobs and /summary."],
        ["Provider defaults", "Default script / TTS / video provider ids."],
        ["Custom providers", "Register your own provider ids (localStorage; future: backend table)."],
      ]),
    ],
    related: ["docker-ports", "custom-providers", "provider-diagnostics"],
  },
  "docker-ports": {
    id: "docker-ports",
    section: "Settings",
    title: "Docker ports",
    summary: "Alt-port mapping for backend / frontend / postgres / redis.",
    body: [
      p("The dev compose maps backend → :8001, frontend → :3010, postgres → :5433, redis → :6380 by default so the stack can coexist with another local dev environment."),
      code(
        "BACKEND_PORT=8001 FRONTEND_PORT=3010 POSTGRES_PORT=5433 REDIS_PORT=6380 \\\n  NEXT_PUBLIC_API_BASE_URL=http://localhost:8001 \\\n  docker compose -f docker/compose.dev.yml up -d",
        "Copy this from Settings → Docker ports.",
        "bash",
      ),
    ],
    related: ["settings"],
  },
  "provider-diagnostics": {
    id: "provider-diagnostics",
    section: "Settings",
    title: "Provider diagnostics (Test1)",
    summary: "Live readiness probes + dry-run generation from the sidebar.",
    body: [
      p("The Test1 sidebar tab shows /api/v1/providers/<category> live + lets you run a one-off generate against the selected provider with a stock payload. No Job is created."),
      kv([
        ["Test (script)", "POST /api/v1/script/generate with a fixed brief."],
        ["Test (tts)", "POST /api/v1/tts/generate with a one-liner."],
        ["Test (video)", "Not yet wired — use /jobs/new for real video."],
      ]),
    ],
    related: ["provider-selection", "errors-glossary"],
  },
  logs: {
    id: "logs",
    section: "Settings",
    title: "Logs panel",
    summary: "Frontend log bus. Session-local — clears on refresh.",
    body: [
      p("The Logs panel records frontend-side events only: failed polls, API errors, action confirmations, setting changes."),
      list([
        "Export JSON / TXT downloads the visible entries.",
        "Clear empties the bus.",
        "There is no backend log persistence today — logs disappear on browser refresh.",
      ]),
    ],
    related: ["provider-diagnostics"],
  },
  "custom-providers": {
    id: "custom-providers",
    section: "Settings",
    title: "Custom providers",
    summary: "Register your own provider ids pointing at a local HTTP endpoint.",
    body: [
      p("Custom providers let you wire a private LLM, a self-hosted TTS, or an external video API into the dashboard without rebuilding the backend."),
      p("Configuration lives in localStorage (per browser). Multi-operator persistence requires a future backend table."),
    ],
    related: ["provider-selection"],
  },
  "errors-glossary": {
    id: "errors-glossary",
    section: "Reference",
    title: "Error glossary",
    summary: "Every error_code the API can return, plus what fixes it.",
    body: [
      kv([
        ["script_provider_disabled", "SCRIPTWRITER_ENABLE_NETWORK_CALLS=true to enable."],
        ["script_model_missing", "`ollama pull <model>` and retry."],
        ["script_provider_unreachable", "Daemon down or OLLAMA_BASE_URL wrong."],
        ["tts_runtime_missing", "Install piper-tts (rebuild with INSTALL_PIPER=true) or start F5TTS-Ro."],
        ["tts_assets_missing", "Drop voice / model files under the configured root."],
        ["tts_generation_failed", "WAV failed validation; check sample rate / channels."],
        ["video_assets_missing", "5 SadTalker weight files not on disk."],
        ["video_gpu_missing", "Driver / Container Toolkit not registered."],
        ["video_runtime_missing", "Use the GPU wrapper, not the light backend."],
        ["provider_not_implemented", "Switch backends or wait for the provider to ship."],
        ["provider_not_configured", "Env var not set."],
      ]),
    ],
    related: ["script-generation", "tts-generation", "sadtalker-video", "recovery-controls"],
  },
  "gpu-runtime": {
    id: "gpu-runtime",
    section: "Infrastructure",
    title: "GPU runtime",
    summary: "Driver, NVIDIA Container Toolkit, Blackwell gotchas.",
    body: [
      list([
        "`nvidia-smi` must list at least one device. If it says no devices, check `lspci -nnk -d 10de:` first — the GPU might be powered down on an Optimus laptop.",
        "`docker run --rm --gpus all nvidia/cuda:12.4.1-runtime-ubuntu22.04 nvidia-smi` must succeed.",
        "Blackwell (RTX 50-series) needs the open-kernel-module driver variant (e.g. nvidia-driver-595-open).",
      ]),
      callout("warn", "Phase 10B confirmed: torch ≥ 2.7 with cu128 wheels is required for sm_120; older torch crashes with `no kernel image is available`.", "Blackwell torch version"),
    ],
    related: ["sadtalker-video", "model-assets"],
  },
  "model-assets": {
    id: "model-assets",
    section: "Infrastructure",
    title: "Model assets",
    summary: "Where weights live, how to install them, and the no-auto-download policy.",
    body: [
      kv([
        ["SadTalker", "models/lipsync/sadtalker/{checkpoints,gfpgan}/ (5 files, ~2 GB)."],
        ["Piper", "models/tts/piper/<voice>/<voice>.onnx + .onnx.json."],
        ["F5TTS-Ro", "models/tts/f5tts-ro/ + reference voice at models/tts/f5tts-ro/reference/voice.wav."],
        ["GFPGAN", "models/lipsync/sadtalker/gfpgan/GFPGANv1.4.pth (333 MB)."],
      ]),
      callout("warn", "ALLOW_MODEL_AUTODOWNLOAD=false is pinned. The backend never auto-fetches weights at build or first run; you place them manually.", "No auto-download"),
    ],
    related: ["sadtalker-video", "piper", "f5tts-ro"],
  },
  "demo-jobs": {
    id: "demo-jobs",
    section: "Reference",
    title: "Demo jobs",
    summary: "Pre-seeded scenarios that exercise every provider path.",
    body: [
      p("`make scenario-jobs` and `make demo-jobs` seed two complementary matrices of jobs — see docs/runbooks/scenario-jobs.md. Phase Demo-RO-1 added a Romanian-themed clean set (Demo RO — …) covering tourism, factory, education, bakery, MP3 conversion, F5TTS-Ro, custom providers, and a real-MP4 SadTalker job."),
      list([
        "Re-running the demo seeder is idempotent — it appends, never duplicates.",
        "Demo jobs never run paid APIs and never auto-pull weights.",
      ]),
    ],
    related: ["jobs-list", "create-job"],
  },
  localization: {
    id: "localization",
    section: "Reference",
    title: "Localization (i18n)",
    summary:
      "Romanian / English UI parity rule, dictionary structure, formatters helper.",
    body: [
      p("Phase 11A introduced the dual EN/RO dictionaries and Phase 11A-FIX completed the cleanup: every operator-visible string lives in `frontend/lib/i18n/dictionaries/{en,ro}.ts`, every Help topic in `frontend/lib/help/dictionaries/{en,ro}.ts`, and runtime enums route through `frontend/lib/i18n/formatters.ts` (tStatus, tStage, tArtifactType, …) so the dashboard never prints raw `pending_compliance` or `tts_provider_not_configured`."),
      kv([
        ["t(path, params)", "Look up a dictionary key. Params replace `{name}` placeholders. Missing keys fall back to English, then to the raw path."],
        ["formatRelativeLocalized(t, iso)", "Bilingual relative time. Replaces the English-only `formatRelative` for any value displayed to the operator."],
        ["localizeApiDetail(t, err)", "Maps known Pydantic / FastAPI error fragments to dictionary keys (synthetic-person, consent, target-duration range, extra-forbidden field, …) and falls back to the raw English text only for unknown shapes."],
        ["tStatus / tStage / tArtifactType / tVoiceMode / tFaceMode / tProviderStatus", "Type-safe enum-to-label helpers. Always pass `t` from `useT()`."],
      ]),
      callout(
        "info",
        "Permanent rule: every new visible label / button / error / status / stage / artifact type / help topic must update BOTH dictionaries in the same PR. Phase 11A-FIX tests enforce key parity and scan for hardcoded English in JSX.",
        "Maintenance rule",
      ),
      list([
        "Allowed English in JSX: provider IDs, API paths, HTTP verbs, file formats (WAV/MP3/PNG/JPEG/MP4/SRT/VTT), env-var names, model names, raw stack traces in log meta.",
        "Use `useT()` even in client components that only show one label — it's free.",
        "When a dictionary value would be byte-identical EN vs RO (e.g. `MP4`), keep it identical — the strict-parity test excludes the known technical allowlist.",
      ]),
    ],
    related: ["settings", "errors-glossary"],
  },
  // -----------------------------------------------------------------
  // Phase 12 — Characters / Personas
  // -----------------------------------------------------------------
  characters: {
    id: "characters",
    section: "Characters",
    title: "Characters tab",
    summary:
      "Reusable personas with identity, appearance, personality, voice + image library.",
    body: [
      p(
        "The Characters tab manages reusable personas you can attach to videos. Each character carries a structured profile (identity, appearance, education, personality, voice, script behaviour) that the scriptwriter, image generator and TTS providers read at job-submit time.",
      ),
      h(3, "Edit & delete behaviour"),
      list([
        "Characters are editable — each save increments the version number and appends a row to character_versions for the snapshot trail.",
        "Delete is a SOFT delete (sets deleted_at) so jobs that referenced the character still resolve.",
        "Old generated videos preserve a frozen snapshot on jobs.character_snapshot — edits / deletes never rewrite history.",
        "Future generations always use the current edited version.",
      ]),
      h(3, "Standardised dropdowns"),
      p(
        "Every standardised field (gender, marital status, education level, archetype, communication style, tone, etc.) pulls its options from /api/v1/characters/lookups. Labels are translatable through the existing useT() hook, so RO / EN follow the global UI language with no rebuild.",
      ),
      callout(
        "info",
        "When a new provider lands (Ollama / F5-TTS / FLUX / SD3.5), it appears automatically in the relevant dropdowns — no frontend code change. Status badges (green / yellow / red) reflect /api/v1/providers in real time.",
        "Dynamic provider registry",
      ),
    ],
    related: ["character-image-library", "character-image-provider", "video-character"],
  },
  "character-image-library": {
    id: "character-image-library",
    section: "Characters",
    title: "Character image library",
    summary:
      "Generate / accept / reference workflow per character.",
    body: [
      p(
        "Each character has its own image library. You generate from a prompt, accept the result, then promote one accepted image to MAIN reference. After a main reference exists, providers that support image-to-image (FLUX BFL, Stability ultra, Replicate FLUX, fal.ai, Midjourney proxy, Recraft) can use it to keep the persona consistent across generations.",
      ),
      h(3, "Statuses"),
      kv([
        ["draft", "Fresh from generation — not yet curated."],
        ["accepted", "Operator approved — eligible to become the main reference."],
        ["rejected", "Operator marked as bad — kept for history, not used."],
        ["reference", "Promoted as the main reference (only one per character)."],
        ["archived", "Hidden from default views; not deleted."],
      ]),
    ],
    related: ["character-image-provider", "characters", "character-main-reference"],
  },
  "character-image-provider": {
    id: "character-image-provider",
    section: "Characters",
    title: "Image generation providers",
    summary:
      "FLUX local (default) + FLUX BFL API + SD3.5 + 13 other backends with status indicators.",
    body: [
      p(
        "The image_generator category lists 16 backends. Only the mock provider runs without operator setup — everything else surfaces a categorised `provider_not_configured` / `runtime_missing` error until you wire the env vars or build the wrapper container.",
      ),
      h(3, "Local GPU wrappers (mirror model-sadtalker)"),
      kv([
        ["flux_local", "FLUX.1-schnell / dev. Set FLUX_LOCAL_BASE_URL + FLUX_LOCAL_MODELS_ROOT."],
        ["sd35_local", "Stable Diffusion 3.5 Large. SD35_LOCAL_BASE_URL + SD35_LOCAL_MODELS_ROOT."],
        ["sdxl_local", "Lighter VRAM alternative. SDXL_LOCAL_BASE_URL."],
        ["comfyui_local", "Bring-your-own workflow JSON. COMFYUI_BASE_URL."],
        ["a1111_local", "AUTOMATIC1111 webui /sdapi/v1. A1111_BASE_URL."],
      ]),
      h(3, "Hosted APIs (env API key only)"),
      kv([
        ["flux_bfl_api", "Black Forest Labs cloud. FLUX_BFL_API_KEY."],
        ["stability_api", "SD3.5 hosted. STABILITY_API_KEY."],
        ["replicate_api", "Multi-model. REPLICATE_API_TOKEN."],
        ["fal_api", "Low-latency hosting. FAL_KEY."],
        ["together_api", "FLUX + community. TOGETHER_API_KEY."],
        ["openai_dalle3", "DALL·E 3. Reuses OPENAI_API_KEY."],
        ["ideogram_api", "IDEOGRAM_API_KEY."],
        ["recraft_api", "RECRAFT_API_KEY."],
        ["vertex_imagen3", "Google Imagen 3. VERTEX_AI_PROJECT_ID + GOOGLE_APPLICATION_CREDENTIALS."],
        ["midjourney_unofficial", "Fragile Discord-bot proxy. MIDJOURNEY_PROXY_URL + MIDJOURNEY_PROXY_TOKEN."],
      ]),
      callout(
        "warn",
        "Outbound API calls require IMAGE_GENERATOR_ENABLE_NETWORK_CALLS=true. Credentials alone are NOT enough to bill an API automatically.",
        "Network gate",
      ),
    ],
    related: ["character-image-library", "providers-overview"],
  },
  "character-main-reference": {
    id: "character-main-reference",
    section: "Characters",
    title: "Main reference image",
    summary:
      "One curated image per character that downstream generations can re-use for image-to-image conditioning.",
    body: [
      p(
        "Promote any accepted image with `Set as main reference`. Providers that advertise reference_image=true in their capabilities can then receive the file path on subsequent generate calls.",
      ),
    ],
    related: ["character-image-library", "character-image-provider"],
  },
  "video-character": {
    id: "video-character",
    section: "Create job",
    title: "Character on the video form",
    summary:
      "The Character dropdown injects a persona profile into the job. Snapshot is frozen at submit time.",
    body: [
      p(
        "Pick a character to forward its identity / language / role / voice provider / image reference into this job. The full profile is snapshotted onto jobs.character_snapshot at submit time — subsequent edits or deletes of the character never rewrite this job's record.",
      ),
    ],
    related: ["characters", "character-image-library"],
  },
  "character-gender": {
    id: "character-gender",
    section: "Characters",
    title: "Gender field",
    summary: "Standardised dropdown drawn from /api/v1/characters/lookups.",
    body: [
      p(
        "Used by the scriptwriter + image prompt builders to keep the persona consistent. Values map to translatable labels via characterLookups.gender.* keys.",
      ),
    ],
  },
  "character-dob": {
    id: "character-dob",
    section: "Characters",
    title: "Date of birth & age",
    summary: "Age is computed from DOB at read time; direct override possible.",
    body: [
      p(
        "Enter a date of birth via the date picker. CharacterProfile.computed_age() returns the derived age in years. If you prefer not to set a DOB, fill the `Age` field directly.",
      ),
    ],
  },
  "character-spoken-languages": {
    id: "character-spoken-languages",
    section: "Characters",
    title: "Spoken languages",
    summary: "Comma-separated list of language codes the persona can speak.",
    body: [
      p(
        "The scriptwriter uses this list to constrain the dialogue language(s). Combined with `voice.preferred_language` to pick the TTS voice.",
      ),
    ],
  },
  "character-education": {
    id: "character-education",
    section: "Characters",
    title: "Education level",
    summary: "Drives the script vocabulary register.",
    body: [
      p(
        "The standardised value (PhD, Master's, Bachelor's, ...) is included in the script prompt context so the LLM matches register.",
      ),
    ],
  },
  "character-archetype": {
    id: "character-archetype",
    section: "Characters",
    title: "Personality archetype",
    summary:
      "High-level archetype blended with tone + values.",
    body: [
      p(
        "Combined with communication style, temperament and tone into a paragraph-shaped briefing the scriptwriter reads via /api/v1/characters/:id/script-context.",
      ),
    ],
  },
  "character-comm-style": {
    id: "character-comm-style",
    section: "Characters",
    title: "Communication style",
    summary: "Formal, informal, conversational, authoritative, persuasive, …",
    body: [
      p(
        "Sets how formal / playful / authoritative the synthesised speech sounds. Combined with the `tone` field for the final voice profile.",
      ),
    ],
  },
  "character-tts-provider": {
    id: "character-tts-provider",
    section: "Characters",
    title: "Preferred TTS provider",
    summary:
      "Defaults the voice provider for any new video tied to this character.",
    body: [
      p(
        "Operator can override per-job. The dropdown lists every provider in /api/v1/providers/tts with a status badge (green = ready, yellow = configured but un-probed, red = unavailable).",
      ),
    ],
  },
  "character-blocked-topics": {
    id: "character-blocked-topics",
    section: "Characters",
    title: "Blocked topics",
    summary:
      "Topic guard-rails the scriptwriter receives explicitly and will refuse to cross.",
    body: [
      p(
        "Comma-separated list. Included in the script context block under `## Safety & topic guard rails` so the LLM sees them in-prompt.",
      ),
    ],
  },
  "providers-overview": {
    id: "providers-overview",
    section: "Providers",
    title: "Dynamic provider registry",
    summary:
      "Every dropdown reads from /api/v1/providers — adding a provider doesn't require a frontend rebuild.",
    body: [
      p(
        "Phase 12 added the dynamic status indicators (green / yellow / red). New providers appear automatically in dropdowns once they're listed in the registry. The status badge reflects env-based readiness + the last health-check probe (POST /api/v1/providers/:category/:id/health-check).",
      ),
      callout(
        "info",
        "Operator overrides live in the feature_providers DB table. Enabled flag, display order, and last health status are merged on top of the code registry at request time — useful to disable a flaky provider without redeploying.",
        "Operator overrides",
      ),
    ],
  },
  // -----------------------------------------------------------------
  // Phase 12X — DB-backed API keys store (right-sidebar Keys tab)
  // -----------------------------------------------------------------
  "api-keys": {
    id: "api-keys",
    section: "Settings",
    title: "API Keys & Endpoints (right-sidebar)",
    summary:
      "Persistent secret store in Postgres. Values load into os.environ at backend startup so they survive Docker restarts.",
    body: [
      p(
        "Open the right-sidebar Keys tab to add / view / test credentials for every hosted provider (FLUX BFL, Stability, Replicate, fal.ai, Together, OpenAI, Ideogram, Recraft, Vertex Imagen, Midjourney proxy) + local wrapper URLs (FLUX, SDXL, SD3.5, ComfyUI, A1111, SadTalker, F5TTS-Ro, Ollama).",
      ),
      h(3, "How it works"),
      list([
        "Each save POSTs /api/v1/secrets/ → persisted in api_secrets table (Postgres).",
        "Backend lifespan hook loads every row into os.environ at startup — adapters that read env vars pick them up unchanged.",
        "Test button runs a cheap reachability probe per credential type (e.g. GET /api/whoami-v2 for HF_TOKEN, GET /v1/models for OpenAI).",
        "Result persists on api_secrets.last_test_status; the green/red dot in the UI reflects the last test outcome.",
        "Per operator request the value field is shown in clear text (not masked).",
      ]),
      h(3, "Endpoints"),
      kv([
        ["GET /api/v1/secrets", "List all persisted secrets + the 24-entry catalog of known keys."],
        ["POST /api/v1/secrets", "Upsert by key_name. Also pushes the value into os.environ immediately."],
        ["PUT /api/v1/secrets/{key_name}", "Update value of an existing secret."],
        ["DELETE /api/v1/secrets/{key_name}", "Soft-remove + drop from os.environ."],
        ["POST /api/v1/secrets/{key_name}/test", "Run the per-key reachability probe."],
      ]),
      callout(
        "info",
        "Hosted provider adapters additionally require IMAGE_GENERATOR_ENABLE_NETWORK_CALLS=true (set via the Keys tab too) before they're allowed to make outbound HTTP calls. Mirror of the SCRIPTWRITER_ENABLE_NETWORK_CALLS gate.",
        "Network gate",
      ),
    ],
    related: ["providers-overview", "character-image-provider"],
  },
  // -----------------------------------------------------------------
  // Phase 12W — Docker GPU wrappers for image generators
  // -----------------------------------------------------------------
  "image-wrappers-docker": {
    id: "image-wrappers-docker",
    section: "Providers",
    title: "Local GPU wrappers (Docker)",
    summary:
      "5 image generators run as sibling Docker containers — FLUX, SDXL, SD3.5, ComfyUI, A1111 (status varies).",
    body: [
      p(
        "Phase 12W added docker/model-flux, model-sdxl, model-sd35, model-comfyui, model-a1111. They mirror the model-sadtalker + model-tts-ro pattern: CUDA base + FastAPI server + read-only models/ mount. Backend adapter posts a generate request, wrapper writes the PNG into the shared artifacts volume.",
      ),
      h(3, "Lifecycle commands"),
      kv([
        ["make docker-flux-build / -up / -down / -logs / -smoke", "FLUX.1-schnell on port 8064."],
        ["make docker-sdxl-build / -up / ...", "Stable Diffusion XL on port 8063."],
        ["make docker-sd35-build / -up / ...", "Stable Diffusion 3.5 Large on port 8065."],
        ["make docker-comfyui-build / -up / ...", "ComfyUI workflow runner on port 8066."],
        ["make docker-a1111-build / -up / ...", "AUTOMATIC1111 WebUI on port 8067."],
      ]),
      h(3, "VRAM management"),
      list([
        "FLUX-schnell + SDXL + SD3.5 each consume 10–22 GB VRAM during inference (with CPU offload). Run one at a time on a 24 GB GPU.",
        "ComfyUI / A1111 keep their model in VRAM idle — stop them between providers if you swap models.",
        "All wrappers use Blackwell-compatible torch 2.7+cu128 for RTX 5090 (sm_120).",
      ]),
      callout(
        "warn",
        "A1111 image is built but its runtime depends on the archived Stability-AI/stablediffusion repo + SD2-era ldm code. The CompVis substitute we vendored covers SD1 ops; SD2 paths (depth model, MMDiT attention modes) crash at first import. Treat the a1111 wrapper as 'image staged, runtime requires operator patch' until a known-good SD2 fork is wired.",
        "A1111 caveat",
      ),
    ],
    related: ["sadtalker-video", "character-image-provider"],
  },
  "video-pipeline": {
    id: "video-pipeline",
    section: "Video",
    title: "Video job pipeline (Characters → SadTalker)",
    summary:
      "End-to-end flow: F5TTS audio + portrait image + character snapshot → orchestrator DAG → SadTalker MP4.",
    body: [
      p(
        "Submitting a video uses POST /api/v1/jobs/from-inputs with audio_artifact_id + image_artifact_id + character_id. The orchestrator runs the canonical DAG (policy_gate → scriptwriter → voice → face → identity_guard → pre_lipsync_auth → lipsync → editor → qc → publisher → export_disclosure_validation). SadTalker generates the MP4 inside the lipsync stage and the artifact is registered on the job.",
      ),
      h(3, "Inputs"),
      list([
        "Audio — F5TTS-Ro generated WAV at /storage/inputs/audio (or operator-uploaded). voice_mode=provided_audio.",
        "Face — uploaded portrait at /storage/inputs/images. face_mode=provided_image.",
        "character_id (optional) — backend snapshots the persona profile onto jobs.character_snapshot at submit time so future edits don't rewrite history. character_videos table gets a link row.",
      ]),
      h(3, "What's persisted"),
      list([
        "jobs row (canonical job lifecycle).",
        "character_videos link (job_id ↔ character_id).",
        "artifacts row pointing at /storage/artifacts/video/{job_id}/sadtalker_*.mp4.",
        "compliance_events + stage_runs for the full audit trail.",
      ]),
      callout(
        "info",
        "Phase 12W bugfix: the agent-* containers (scriptwriter / editor / qc / publisher / compliance) used to lack the /storage volume mounts so voice stage failed with 'audio file not found'. Compose now mounts inputs_data + artifacts_data + ../models on every agent.",
        "Storage mount fix",
      ),
    ],
    related: ["video-character", "sadtalker-video", "characters"],
  },
  // -----------------------------------------------------------------
  // Phase 12T — Technical Help page
  // -----------------------------------------------------------------
  "technical-help": {
    id: "technical-help",
    section: "Reference",
    title: "Technical Help page",
    summary:
      "Live render of docs/TECHNICAL_ARCHITECTURE.md served by the backend; searchable with table-of-contents and Markdown download.",
    body: [
      p(
        "Open via the 'Technical' nav entry or the /technical-help route. The page fetches GET /api/v1/system/technical-architecture and renders the Markdown with a sticky search box. Hits are highlighted across paragraphs, lists, tables and code blocks; the TOC follows level-1 and level-2 headings.",
      ),
      h(3, "Endpoints"),
      kv([
        ["GET /api/v1/system/technical-architecture", "JSON envelope: title, source_path, size_bytes, markdown, generated_at."],
        ["GET /api/v1/system/technical-architecture.md", "Raw Markdown (text/markdown). Used by the Download Markdown link."],
      ]),
      h(3, "Why it lives on disk"),
      list([
        "Source of truth is docs/TECHNICAL_ARCHITECTURE.md in the repo so it is versioned with the code.",
        "Backend Dockerfile copies it into /app/docs/ so the endpoint can read it without a runtime mount.",
        "Edits in the file ship in the next backend image build — no DB migration required.",
      ]),
      callout(
        "info",
        "Use the search box for fast lookups: provider names, port numbers, env vars, migration revs, table names. Hits scroll into view; the TOC hides while a query is active.",
        "Search tips",
      ),
    ],
    related: ["api-keys", "providers-overview", "video-pipeline"],
  },
};

export const HELP_TOPIC_IDS_EN: readonly string[] = Object.keys(HELP_TOPICS_EN);
