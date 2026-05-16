// Authored help content. One file so it's trivial to grep, version,
// and translate later. Articles are grouped by ``section`` — the
// HelpOverlay renders the section tree from this data alone.

import type { HelpArticle, HelpSection } from "./types";

export const HELP_SECTIONS: readonly HelpSection[] = [
  {
    id: "start",
    title: "Get started",
    description:
      "What P1.AIVideo is, why it exists, and how to ship your first reel.",
    order: 1,
  },
  {
    id: "ui",
    title: "Tour the dashboard",
    description: "Every page, panel, and button explained.",
    order: 2,
  },
  {
    id: "jobs",
    title: "Jobs & workflow",
    description: "Lifecycle, stages, retries, and recovery.",
    order: 3,
  },
  {
    id: "inputs",
    title: "Inputs & uploads",
    description: "Bring your own image, audio, or text.",
    order: 4,
  },
  {
    id: "providers",
    title: "Providers",
    description:
      "Script, TTS, image and video backends — what's available and how to pick.",
    order: 5,
  },
  {
    id: "video",
    title: "Video / lip-sync",
    description:
      "SadTalker, MuseTalk and Wav2Lip integrations, plus GPU prerequisites.",
    order: 6,
  },
  {
    id: "voice",
    title: "Voice / TTS",
    description: "Piper, F5TTS-Ro, and provided-audio mode.",
    order: 7,
  },
  {
    id: "compliance",
    title: "Compliance & policy",
    description: "Synthetic-only rule, AI disclosure, watermark, C2PA.",
    order: 8,
  },
  {
    id: "infra",
    title: "Infrastructure",
    description: "Docker stack, profiles, volumes, environment.",
    order: 9,
  },
  {
    id: "troubleshooting",
    title: "Troubleshooting",
    description: "Symptoms, root causes, fixes.",
    order: 10,
  },
  {
    id: "reference",
    title: "Reference",
    description: "Glossary, error codes, keyboard shortcuts, API.",
    order: 11,
  },
];

export const HELP_ARTICLES: readonly HelpArticle[] = [
  // ===========================================================================
  // SECTION: start
  // ===========================================================================
  {
    slug: "welcome",
    title: "Welcome to P1.AIVideo",
    section: "start",
    summary:
      "Short-form reel generator for synthetic personas. Strict compliance, multi-agent DAG, fully local.",
    keywords: [
      "overview",
      "intro",
      "welcome",
      "what is",
      "p1",
      "aivideo",
      "purpose",
    ],
    body: [
      {
        type: "p",
        text: "P1.AIVideo turns a short brief into a complete short-form reel: a written script, a synthesized narration, a synthetic-person portrait, a lip-synced video, a quality-control report, and a final published bundle — all produced through a deterministic multi-agent pipeline.",
      },
      {
        type: "p",
        text: "The operator never sees a real person. Every face is AI-generated; every voice is either provided by the operator or synthesised. Real-person likeness and voice cloning are blocked at the contract layer, not at runtime — the API rejects them up-front with categorised error codes.",
      },
      { type: "h", level: 3, text: "What this app is good at" },
      {
        type: "list",
        items: [
          "Producing reproducible 15–60 second reels for marketing / education / demos.",
          "Running the full ML stack on a single GPU host, in Docker, without external API calls.",
          "Surfacing every readiness gap (missing weights, missing runtime, no GPU, expired compliance token) as a structured response — never a 500.",
          "Snapshotting every artifact (script, audio, video, edit plan, QC, export) with a sha256 checksum so audit trails are tamper-evident.",
        ],
      },
      { type: "h", level: 3, text: "What it is not" },
      {
        type: "list",
        items: [
          "Not a real-person deepfake tool. The provider layer refuses to synthesise without a synthetic_person_confirmed flag.",
          "Not a hosted SaaS — this is the operator dashboard for a stack you run yourself.",
          "Not magic — if the weights / runtime / GPU aren't on the host, the dashboard tells you which one is missing, not what to do about it.",
        ],
      },
      { type: "spacer" },
      { type: "linkArticle", slug: "quickstart", label: "Next: 5-minute quick start →" },
    ],
    related: ["quickstart", "core-concepts", "synthetic-only"],
  },
  {
    slug: "quickstart",
    title: "Quick start (5 minutes)",
    section: "start",
    summary:
      "Run the light stack, create a job, watch it move through the DAG.",
    keywords: ["quick", "start", "first job", "minimum", "tutorial"],
    body: [
      { type: "h", level: 3, text: "1. Bring up the light stack" },
      {
        type: "code",
        lang: "bash",
        text: "make docker-light-build\nmake docker-light-up\nmake docker-light-smoke",
        caption: "Builds + starts postgres / redis / backend / frontend / orchestrator. No GPU yet.",
      },
      {
        type: "p",
        text: "Dashboard appears on http://localhost:3001 (or whatever FRONTEND_PORT you set). The backend is on http://localhost:8001.",
      },
      { type: "h", level: 3, text: "2. Open the dashboard" },
      {
        type: "p",
        text: "The top-right Backend status badge should read \"healthy\". If it's red, see Troubleshooting → backend unreachable.",
      },
      { type: "h", level: 3, text: "3. Create a job" },
      {
        type: "list",
        ordered: true,
        items: [
          "Click \"New job\" in the header.",
          "Type a brief in your own words (1–2 sentences).",
          "Tick \"Synthetic person confirmed\" and \"Consent confirmed\" — both are mandatory.",
          "Optionally upload a reference image and / or audio from the Uploads page first and link them here.",
          "Pick providers (Script / Voice / Video) or accept the defaults.",
          "Submit. The job moves to pending_compliance.",
        ],
      },
      { type: "h", level: 3, text: "4. Watch it run" },
      {
        type: "p",
        text: "Open the job detail page. The Timeline card shows each stage transitioning pending → running → succeeded. The Artifacts table fills in as each stage produces files.",
      },
      {
        type: "callout",
        tone: "info",
        title: "Light stack limits",
        text: "The default stack runs scriptwriting + compliance + scaffolding only. Real TTS needs piper installed; real video needs the SadTalker GPU profile. See Video → SadTalker setup once you want a real MP4.",
      },
      { type: "spacer" },
      { type: "linkArticle", slug: "sadtalker-setup", label: "Next: produce a real MP4 →" },
    ],
    related: ["sadtalker-setup", "f5tts-ro-setup", "job-lifecycle"],
  },
  {
    slug: "core-concepts",
    title: "Core concepts",
    section: "start",
    summary: "Job, artifact, stage, provider, compliance token — the vocabulary used everywhere.",
    keywords: ["concept", "glossary", "job", "stage", "artifact", "dag", "vocabulary"],
    body: [
      {
        type: "kv",
        caption: "Vocabulary",
        rows: [
          ["Job", "One end-to-end request to produce a reel. Has a status (pending_compliance / accepted / published / rejected / failed) and a sequence of stage runs."],
          ["DAG", "The directed graph the orchestrator walks: compliance → identity_guard → scriptwriter → voice → face → pre_lipsync_auth → lipsync → editor → qc → publisher."],
          ["Stage", "One node in the DAG, with its own provider, its own artifact contract, and its own success / rejection codes."],
          ["Artifact", "A typed output produced by a stage. Always has sha256, mime_type, size, and either an inline JSON blob or a local_path on disk."],
          ["Provider", "A pluggable backend (Piper, SadTalker, Ollama, F5TTS-Ro, …). Each provider declares its own readiness gates."],
          ["Compliance token", "A short-lived HMAC token the compliance officer mints once per job and the lipsync stage verifies before invoking any model. Prevents replay attacks."],
          ["Readiness gate", "A pre-flight check (runtime importable, GPU visible, weights on disk, opt-in flags set). Every provider exposes its gates via /api/v1/providers/*."],
          ["Categorised error", "A response with a structured error_code (e.g. video_assets_missing). The frontend pattern-matches on these so users see what to fix, not a stack trace."],
        ],
      },
      { type: "linkArticle", slug: "job-lifecycle", label: "Read on: Job lifecycle →" },
    ],
    related: ["job-lifecycle", "compliance-overview", "providers-catalog"],
  },
  {
    slug: "synthetic-only",
    title: "Synthetic-only rule",
    section: "start",
    summary: "Why every job demands \"synthetic person confirmed\". What that flag means.",
    keywords: ["synthetic", "compliance", "consent", "policy", "no real person", "deepfake"],
    body: [
      {
        type: "p",
        text: "P1.AIVideo refuses to produce content depicting a real person's likeness or cloning a real person's voice. This is enforced at three layers:",
      },
      {
        type: "list",
        ordered: true,
        items: [
          "Schema layer — JobCreateRequest requires synthetic_person_confirmed=true and consent_confirmed=true. The API rejects the job at validation time otherwise.",
          "Compliance stage — the compliance officer revalidates inputs and refuses if any artifact carries metadata flagging a real-person source.",
          "Provider layer — face / lipsync providers refuse to load reference images that fail synthetic-likeness heuristics (where available).",
        ],
      },
      {
        type: "callout",
        tone: "warn",
        title: "Operator responsibility",
        text: "The flags are operator-attested. Setting them on a real-person image bypasses the schema layer but the compliance event log still records the attestation; this is your audit trail.",
      },
      {
        type: "p",
        text: "Every published reel carries a mandatory AI-content disclosure on the final export — see Compliance → AI disclosure.",
      },
    ],
    related: ["compliance-overview", "compliance-watermark-c2pa"],
  },

  // ===========================================================================
  // SECTION: ui — pages tour
  // ===========================================================================
  {
    slug: "page-dashboard",
    title: "Dashboard (/) — at a glance",
    section: "ui",
    summary: "Stack health, latest jobs, quick links.",
    keywords: ["dashboard", "home", "/", "landing"],
    body: [
      {
        type: "p",
        text: "The root route is a thin landing page that summarises stack health and links to the main flows.",
      },
      {
        type: "list",
        items: [
          "Top header shows the global Backend status badge (green/yellow/red).",
          "Quick links jump to Jobs / New job / Uploads / Settings.",
          "Activity sidebar (right) is collapsible — keep it open while debugging, collapse it for screen real estate.",
        ],
      },
      { type: "linkArticle", slug: "page-jobs-list", label: "Next: Jobs list →" },
    ],
    related: ["page-jobs-list", "right-sidebar"],
  },
  {
    slug: "page-jobs-list",
    title: "Jobs list (/jobs)",
    section: "ui",
    summary: "Browse all jobs. Filter by status. Drill into details.",
    keywords: ["jobs", "list", "table", "filter", "search"],
    body: [
      {
        type: "p",
        text: "The Jobs page is the operational table-of-contents. Rows show id, brief, current stage, status, and creation time.",
      },
      { type: "h", level: 3, text: "Columns" },
      {
        type: "kv",
        rows: [
          ["Brief", "First 60 chars of the operator brief. Click the row to drill in."],
          ["Status", "pending_compliance / accepted / published / rejected / failed. Color-coded chip."],
          ["Stage", "Currently running stage, or last completed for terminal jobs."],
          ["Progress", "Percentage of stages completed out of the total DAG."],
          ["Created", "When the job was POSTed."],
        ],
      },
      { type: "h", level: 3, text: "Quick actions" },
      {
        type: "list",
        items: [
          "Status filter at the top trims the table without re-fetching everything.",
          "Click \"New job\" to create one without leaving the page.",
          "The list is sorted by created_at desc; newest at the top.",
        ],
      },
    ],
    related: ["page-job-detail", "page-create-job"],
  },
  {
    slug: "page-job-detail",
    title: "Job detail (/jobs/[jobId])",
    section: "ui",
    summary: "Everything about one job: timeline, artifacts, compliance, QC, export, recovery.",
    keywords: ["job", "detail", "timeline", "artifacts", "qc", "recovery"],
    body: [
      {
        type: "p",
        text: "The job-detail page is the single source of truth for one reel. It is composed of stacked cards, each safe to refresh independently.",
      },
      { type: "h", level: 3, text: "Cards (top to bottom)" },
      {
        type: "kv",
        rows: [
          ["Header", "Brief, status chip, target duration, voice / face mode, edit / cancel / retry buttons."],
          ["Progress bar", "Polls every few seconds; advances as stages succeed."],
          ["Stage timeline", "All 10 DAG stages with their status, duration, and rejection reason if any."],
          ["Artifacts table", "Every artifact registered against the job, with type / size / duration / dims / download link."],
          ["Video preview", "Inline <video> for any artifact with mime_type=video/mp4. Falls back to a Download link if the browser can't decode."],
          ["Compliance events", "Every accept / reject / token issuance with the timestamp and reason."],
          ["QC report", "Lip-sync confidence, watermark presence, AI disclosure status, decision (pass / warn / fail)."],
          ["Final export card", "Published vs blocked; embeds the AI disclosure metadata and C2PA signing status."],
          ["Recovery controls", "Reset the job, retry from a specific stage, or cancel."],
        ],
      },
      {
        type: "callout",
        tone: "info",
        text: "Polling is paused while the browser tab is hidden, so the UI doesn't hammer the backend in the background.",
      },
    ],
    related: ["job-lifecycle", "stage-timeline", "artifact-types", "page-job-edit"],
  },
  {
    slug: "page-job-edit",
    title: "Edit job (/jobs/[jobId]/edit)",
    section: "ui",
    summary: "Mutate brief, duration, providers and compliance flags on a non-terminal job.",
    keywords: ["edit", "patch", "job", "mutate"],
    body: [
      {
        type: "p",
        text: "Editing is allowed for jobs in pending_compliance or accepted; once a job is published / rejected / failed the form blocks edits.",
      },
      { type: "h", level: 3, text: "Editable fields" },
      {
        type: "list",
        items: [
          "brief (free text, 6–800 chars)",
          "target_duration_seconds (15–60)",
          "voice_mode + tts_backend + script_text",
          "image_ref + face_mode",
          "provider_selection.{script_provider_id, voice_provider_id, video_provider_id}",
          "watermark_required, c2pa_required (cannot be set to false — the form refuses the patch)",
        ],
      },
      {
        type: "callout",
        tone: "warn",
        text: "Saving a patch invalidates any in-flight stage runs. The orchestrator picks the job up again from the earliest invalidated stage; older artifacts stay attached for traceability.",
      },
    ],
    related: ["page-job-detail", "page-create-job"],
  },
  {
    slug: "page-create-job",
    title: "New job (/jobs/new)",
    section: "ui",
    summary: "Multi-tab form: brief → inputs → providers → compliance → submit.",
    keywords: ["create", "new", "submit", "form", "wizard"],
    body: [
      {
        type: "p",
        text: "The CreateJobForm is a tabbed wizard. Each tab validates locally before letting you proceed; nothing is sent to the backend until you submit.",
      },
      { type: "h", level: 3, text: "Tabs" },
      {
        type: "kv",
        rows: [
          ["Brief", "Free-text description + target duration. The scriptwriter uses this as the prompt."],
          ["Voice", "Pick TTS mode (synthesise) or provided audio (upload first, then reference the artifact id)."],
          ["Face", "Provided image only (synthetic person). Upload first under Uploads."],
          ["Providers", "Override the deploy defaults — script / voice / video provider ids. Leave blank to inherit."],
          ["Compliance", "The two mandatory attestations. The submit button stays disabled until both are ticked."],
        ],
      },
      {
        type: "p",
        text: "Image / audio refs are sent as full ref objects (type=local_path, path, mime_type, checksum). The form builds those from the artifact you select; you don't have to hand-craft the JSON.",
      },
    ],
    related: ["page-uploads", "providers-catalog", "compliance-overview"],
  },
  {
    slug: "page-uploads",
    title: "Uploads (/uploads)",
    section: "ui",
    summary: "Drop images, audio, or text and turn them into reusable artifact refs.",
    keywords: ["upload", "image", "audio", "text", "intake"],
    body: [
      {
        type: "p",
        text: "Uploads are first-class artifacts — they get a sha256, a stable id, and live under the artifacts_data named volume just like generated outputs. Multiple jobs can reference the same uploaded ref.",
      },
      { type: "h", level: 3, text: "Allowed types" },
      {
        type: "kv",
        rows: [
          ["Image", "image/png, image/jpeg. Min 256×256 for SadTalker; portraits closer to 1024×1024 give the best 3DMM extraction."],
          ["Audio", "audio/wav (PCM). MP3 / M4A are auto-converted server-side via ffmpeg; the converted .wav is what the pipeline references."],
          ["Text", "Plain text (UTF-8) for script overrides, captions, or notes."],
        ],
      },
      {
        type: "callout",
        tone: "info",
        title: "MIME hints",
        text: "If your file comes through as application/octet-stream the API rejects it. Use `-F \"file=@path;type=audio/wav\"` with curl, or let the browser dialog set the type.",
      },
    ],
    related: ["inputs-images", "inputs-audio"],
  },
  {
    slug: "page-settings",
    title: "Settings (/settings)",
    section: "ui",
    summary: "Deploy-level defaults, custom providers, UI preferences.",
    keywords: ["settings", "preferences", "defaults", "custom providers"],
    body: [
      { type: "h", level: 3, text: "Sections" },
      {
        type: "kv",
        rows: [
          ["Defaults", "Default script / voice / video provider ids. The CreateJobForm pre-fills from these."],
          ["Custom providers", "Register your own provider ids. Useful when running a private LLM behind an OpenAI-compatible endpoint."],
          ["UI", "Right-sidebar default state, polling interval, theme accent."],
        ],
      },
      {
        type: "p",
        text: "All UI settings are persisted in localStorage; deploy defaults round-trip to backend env vars (read-only here — change them in .env to make them sticky across restarts).",
      },
    ],
    related: ["providers-custom", "right-sidebar"],
  },
  {
    slug: "right-sidebar",
    title: "Right sidebar — Logs / Settings / Test1",
    section: "ui",
    summary: "Always-on diagnostic panel.",
    keywords: ["sidebar", "logs", "panel", "diagnostics", "test", "right"],
    body: [
      {
        type: "p",
        text: "The right sidebar is a sticky panel with three tabs that survive across pages. State persists in localStorage so it's exactly how you left it when you come back.",
      },
      {
        type: "kv",
        rows: [
          ["Logs", "Streams the in-page log bus (frontend events: polling errors, API failures, action confirmations). Toggle levels with the chips at the top."],
          ["Settings", "Same content as /settings — quicker access without leaving the current job."],
          ["Test1", "Provider diagnostics. Hit a provider, see its raw response, copy as curl. Great for reproducing categorised errors."],
        ],
      },
      {
        type: "p",
        text: "Collapse the sidebar with « to free horizontal space; rail labels stay visible so you can re-open any tab in one click.",
      },
    ],
    related: ["page-settings", "logs-panel"],
  },
  {
    slug: "logs-panel",
    title: "Logs panel",
    section: "ui",
    summary: "Frontend log bus — what gets recorded, how to copy / export.",
    keywords: ["logs", "panel", "events", "console"],
    body: [
      {
        type: "p",
        text: "The Logs panel records frontend-side events only — backend logs live in `docker compose logs`. It's intended for: which polling call failed, which API returned a categorised error, when a setting was persisted, etc.",
      },
      {
        type: "list",
        items: [
          "Each entry has a timestamp, level (info / warn / error), source, and message.",
          "Click an entry to expand its payload (any structured object the call site attached).",
          "Use the level chips at the top to filter; the export button dumps the visible entries as JSON.",
        ],
      },
    ],
    related: ["right-sidebar", "troubleshooting-frontend"],
  },

  // ===========================================================================
  // SECTION: jobs
  // ===========================================================================
  {
    slug: "job-lifecycle",
    title: "Job lifecycle — the 10-stage DAG",
    section: "jobs",
    summary: "Every stage, in order, with its job and its failure modes.",
    keywords: ["lifecycle", "dag", "stages", "pipeline", "workflow"],
    body: [
      {
        type: "p",
        text: "Each job walks a fixed directed acyclic graph. Stages run in order; a rejection from any stage halts the job and writes the reason to compliance_events.",
      },
      {
        type: "kv",
        caption: "Stages in order",
        rows: [
          ["compliance", "Validates synthetic_person_confirmed, consent_confirmed, watermark + c2pa flags. Issues nothing — only accepts or rejects."],
          ["identity_guard", "Heuristic scan of any provided image/audio for real-person fingerprints. Soft check — operator attestation still wins."],
          ["scriptwriter", "Produces a structured script artifact (hook / body / cta / language). Uses the configured script provider."],
          ["voice", "Synthesises narration (TTS providers) OR validates provided audio. Output: ArtifactType.audio with checksum + duration."],
          ["face", "Synthesises (or validates provided) portrait. Output: ArtifactType.image with width / height."],
          ["pre_lipsync_auth", "Mints the compliance token the lipsync provider will check before invoking any model."],
          ["lipsync", "Generates the talking-head MP4 via SadTalker / MuseTalk / Wav2Lip. Heaviest stage — GPU required."],
          ["editor", "Stitches the MP4 + audio, builds an edit_plan artifact (cuts, transitions, captions)."],
          ["qc", "Runs lip-sync confidence + watermark + AI-disclosure checks. Emits a QC report with pass / warn / fail."],
          ["publisher", "Final export bundle. Embeds the AI disclosure, signs with C2PA if c2pa_required=true."],
        ],
      },
      {
        type: "callout",
        tone: "info",
        text: "Stages are idempotent: re-running a stage replaces its artifact rather than appending a new one. This makes Recovery → \"retry from stage X\" safe.",
      },
    ],
    related: ["stage-timeline", "stage-rejections", "compliance-overview"],
  },
  {
    slug: "stage-timeline",
    title: "Reading the stage timeline",
    section: "jobs",
    summary: "What the colors, durations, and chevrons mean.",
    keywords: ["timeline", "stage", "status", "duration"],
    body: [
      {
        type: "kv",
        caption: "Status chips",
        rows: [
          ["pending", "Has not started yet. Waiting for an upstream stage."],
          ["running", "Currently executing. Spinner overlay."],
          ["succeeded", "Done; produced its artifact."],
          ["failed", "An unexpected exception was raised. See the inline message for the type + traceback tail."],
          ["rejected", "A categorised contract failure (e.g. video_assets_missing). The error_code tells you exactly which gate failed."],
          ["skipped", "DAG decided this stage didn't apply (e.g. voice stage when voice_mode=provided_audio with a pre-validated WAV)."],
        ],
      },
      {
        type: "p",
        text: "Duration is wall-clock seconds. SadTalker typically reports 60–150 s on an RTX 5090 for a 15 s reel; numbers way outside that range hint at GPU contention or model thrashing.",
      },
    ],
    related: ["stage-rejections", "video-troubleshoot"],
  },
  {
    slug: "stage-rejections",
    title: "Why stages get rejected",
    section: "jobs",
    summary: "Top rejection categories and what to do about each.",
    keywords: ["reject", "rejected", "failure", "error", "stage"],
    body: [
      {
        type: "kv",
        rows: [
          ["compliance_attestation_missing", "Job is missing synthetic_person_confirmed / consent_confirmed. Edit the job to flip them."],
          ["script_provider_not_implemented", "Configured script provider isn't wired. Switch to `template` (always works) under Settings → Defaults."],
          ["tts_runtime_missing", "TTS provider's runtime (piper / f5_tts) isn't installed. Install it or pick provided_audio voice mode."],
          ["tts_assets_missing", "Voice weights aren't on disk under PIPER_MODELS_ROOT / F5TTS_RO_MODELS_ROOT."],
          ["video_assets_missing", "SadTalker weights aren't on disk. See Video → SadTalker setup."],
          ["video_runtime_missing", "torch / sadtalker not importable in the agent image. Use the GPU profile (model-sadtalker)."],
          ["video_gpu_missing", "torch present but no CUDA device. Check `nvidia-smi` + NVIDIA Container Toolkit."],
          ["compliance_token_invalid", "lipsync stage's token expired or its signing key doesn't match the issuer's. Restart both services so they share COMPLIANCE_SIGNING_KEY."],
          ["qc_lipsync_confidence_low", "lip-sync confidence below threshold. Re-shoot with a clearer portrait + cleaner audio."],
          ["publisher_disclosure_missing", "AI disclosure metadata didn't land. Re-run the publisher stage; this is almost always a transient file-system permission issue."],
        ],
      },
      {
        type: "linkArticle",
        slug: "error-codes",
        label: "See the full error-codes reference →",
      },
    ],
    related: ["error-codes", "job-recovery"],
  },
  {
    slug: "job-recovery",
    title: "Recovering a failed / rejected job",
    section: "jobs",
    summary: "Retry, reset, or cancel without losing earlier artifacts.",
    keywords: ["recovery", "retry", "reset", "cancel", "rerun"],
    body: [
      { type: "h", level: 3, text: "From the UI" },
      {
        type: "list",
        items: [
          "\"Retry from stage…\" — pick the earliest stage you want to redo. Earlier artifacts stay attached.",
          "\"Reset to compliance\" — sets status back to pending_compliance, drops every stage run. Inputs (image_ref, audio_ref) are kept.",
          "\"Cancel\" — terminal, sets status=failed with reason=operator_cancelled.",
        ],
      },
      { type: "h", level: 3, text: "Equivalent API calls" },
      {
        type: "code",
        lang: "bash",
        text: "curl -sS -X POST http://localhost:8001/api/v1/jobs/<id>/retry \\\n  -H 'Content-Type: application/json' \\\n  -d '{\"from_stage\":\"lipsync\"}'\n\ncurl -sS -X POST http://localhost:8001/api/v1/jobs/<id>/cancel",
      },
      {
        type: "callout",
        tone: "warn",
        text: "Reset / retry never delete artifacts off disk — they only un-link them from the active stage_run. Use the Artifacts table to clean up manually if storage matters.",
      },
    ],
    related: ["stage-rejections", "page-job-detail"],
  },

  // ===========================================================================
  // SECTION: inputs
  // ===========================================================================
  {
    slug: "inputs-images",
    title: "Image inputs",
    section: "inputs",
    summary: "PNG / JPEG portraits, what dimensions work, what gets rejected.",
    keywords: ["image", "portrait", "png", "jpeg", "input", "upload"],
    body: [
      { type: "h", level: 3, text: "Format requirements" },
      {
        type: "kv",
        rows: [
          ["Allowed MIME", "image/png, image/jpeg"],
          ["Min dimensions", "Practical floor 256×256 (SadTalker face detection); ideal 1024×1024 portrait, face centered."],
          ["Max upload size", "Configured via UPLOAD_IMAGE_MAX_BYTES (default 20 MB)."],
          ["Color", "RGB. RGBA is converted server-side (alpha discarded)."],
        ],
      },
      { type: "h", level: 3, text: "What the pipeline does with it" },
      {
        type: "list",
        ordered: true,
        items: [
          "Compute sha256 + measure width/height + persist under /storage/inputs/images.",
          "Register an ArtifactType.image row with metadata_summary.phase=phase4a2_upload_image.",
          "The face stage either re-validates (provided image) or feeds the image to the lipsync provider as source_image.",
        ],
      },
      {
        type: "callout",
        tone: "info",
        title: "Tip — synthetic-person sources",
        text: "thispersondoesnotexist.com produces CC0 AI faces that pass synthetic-only attestation. Save the JPEG and upload it.",
      },
    ],
    related: ["page-uploads", "compliance-overview"],
  },
  {
    slug: "inputs-audio",
    title: "Audio inputs",
    section: "inputs",
    summary: "WAV mandatory, MP3 / M4A auto-converted, duration limits.",
    keywords: ["audio", "wav", "mp3", "m4a", "tts", "input", "upload"],
    body: [
      {
        type: "kv",
        rows: [
          ["Native format", "audio/wav, PCM, 16 / 22.05 / 44.1 / 48 kHz, mono or stereo."],
          ["Auto-conversion", "audio/mpeg, audio/mp4, audio/x-wav routed through ffmpeg → mono WAV at the original sample rate. Original kept under inputs_data as well."],
          ["Min duration", "1 s (validated by audio_validation)."],
          ["Max duration", "AUDIO_MAX_DURATION_SECONDS (default 600 s = 10 min)."],
        ],
      },
      {
        type: "callout",
        tone: "warn",
        title: "0.3 s placeholder files",
        text: "The legacy demo seeds include 13 KB WAVs whose duration is 0.3 s. SadTalker needs at least a few seconds of audio to produce a meaningful talking head — use real or synthesised audio for real runs.",
      },
    ],
    related: ["page-uploads", "voice-piper", "voice-f5tts-ro"],
  },

  // ===========================================================================
  // SECTION: providers
  // ===========================================================================
  {
    slug: "providers-catalog",
    title: "Provider catalog",
    section: "providers",
    summary: "Browse the provider registry and what each row means.",
    keywords: ["provider", "catalog", "registry", "list", "backend"],
    body: [
      {
        type: "p",
        text: "Each provider category is exposed at /api/v1/providers/<category>. Rows describe a backend the pipeline can plug into: a name, a status, a category, and a notes string with the live readiness state.",
      },
      { type: "h", level: 3, text: "Categories" },
      {
        type: "kv",
        rows: [
          ["script", "Brief → structured script. Backends: template (deterministic), ollama (network LLM)."],
          ["tts", "Text → audio. Backends: piper, f5tts_ro, coqui_tts, xtts, styletts, elevenlabs_compatible, openai_compatible_tts, local_http_tts."],
          ["image", "Synthetic portrait. Backends: synthetic_local (placeholder), external_image_api."],
          ["video", "Image + audio → MP4. Backends: sadtalker (Phase 10B real), musetalk, wav2lip, liveportrait, local_http_video, external_video_api."],
          ["audio-processors", "FFmpeg-based audio fit-check, normalisation, conversion."],
          ["image-processors", "Crop, resize, watermark embedding."],
        ],
      },
      { type: "linkArticle", slug: "providers-status", label: "Next: status codes →" },
    ],
    related: ["providers-status", "providers-custom"],
  },
  {
    slug: "providers-status",
    title: "Provider status codes",
    section: "providers",
    summary: "ok, not_implemented, not_configured, missing_assets, runtime_missing, gpu_unavailable.",
    keywords: ["status", "provider", "ok", "not implemented", "ready", "healthcheck"],
    body: [
      {
        type: "kv",
        rows: [
          ["ok / ready", "Everything required is present. The provider will actually run."],
          ["not_implemented", "Default placeholder. The provider's adapter is wired but the heavy path is deliberately stubbed. Switch backends or wait for the next phase."],
          ["not_configured", "The provider's required env var (PIPER_MODELS_ROOT, F5TTS_RO_BASE_URL, …) is unset. See the row's notes field for the exact var."],
          ["missing_assets / assets_missing", "Env vars OK but the weights aren't on disk. notes lists the missing relative paths."],
          ["runtime_missing", "Weights present but the Python library (piper, f5_tts, torch, sadtalker) isn't importable in the current image. Build / install the heavy variant."],
          ["gpu_unavailable", "torch loaded but cuda.is_available() returned False. Driver / Container Toolkit / Optimus situation; see Infrastructure → GPU prerequisites."],
        ],
      },
      {
        type: "callout",
        tone: "info",
        text: "The Right sidebar → Test1 tab lets you hit any provider's healthcheck endpoint without leaving the page. Use it to validate fixes in real time.",
      },
    ],
    related: ["providers-catalog", "video-troubleshoot", "infra-gpu"],
  },
  {
    slug: "providers-custom",
    title: "Custom providers",
    section: "providers",
    summary: "Register your own provider_id pointing at a local HTTP endpoint or external API.",
    keywords: ["custom", "provider", "openai compatible", "byoa", "register"],
    body: [
      {
        type: "p",
        text: "Custom providers let you wire a private LLM, a self-hosted TTS, or an external video API into the dashboard without rebuilding the backend.",
      },
      { type: "h", level: 3, text: "From the UI" },
      {
        type: "list",
        ordered: true,
        items: [
          "Open /settings → Custom providers.",
          "Click \"Add provider\", pick a category and a unique provider_id.",
          "Fill in the base_url and any auth headers (stored locally + sent through the backend's proxy).",
          "Use the Test panel to hit the provider's /health or equivalent and confirm 200.",
        ],
      },
      {
        type: "callout",
        tone: "info",
        title: "Where it lives",
        text: "Custom provider config is stored in localStorage AND (when persistence is enabled) round-tripped to a backend table. localStorage is the source of truth on the client.",
      },
    ],
    related: ["providers-catalog", "page-settings"],
  },

  // ===========================================================================
  // SECTION: video
  // ===========================================================================
  {
    slug: "video-overview",
    title: "Video / lip-sync overview",
    section: "video",
    summary: "Three backends, all GPU-only, all opt-in.",
    keywords: ["video", "lipsync", "lip sync", "sadtalker", "musetalk", "wav2lip"],
    body: [
      {
        type: "kv",
        rows: [
          ["SadTalker (v1)", "Production-default. Realistic head motion + GFPGAN face restore. ~120 s per 15 s reel on RTX 5090."],
          ["MuseTalk (v2)", "Newer architecture, better mouth shapes — wiring pending."],
          ["Wav2Lip", "Faster, lower-fidelity fallback. Useful when SadTalker can't find a face."],
          ["LivePortrait", "Research-grade. Deferred."],
        ],
      },
      {
        type: "callout",
        tone: "warn",
        text: "All four are GPU-only. The default light backend never runs them; you must start the appropriate Docker profile.",
      },
      { type: "linkArticle", slug: "sadtalker-setup", label: "Next: SadTalker setup →" },
    ],
    related: ["sadtalker-setup", "infra-gpu"],
  },
  {
    slug: "sadtalker-setup",
    title: "SadTalker setup (Phase 10B)",
    section: "video",
    summary: "Weights, GPU wrapper, env vars, and the docker-sadtalker make targets.",
    keywords: ["sadtalker", "setup", "phase 10b", "gpu", "weights"],
    body: [
      { type: "h", level: 3, text: "Prerequisites" },
      {
        type: "list",
        items: [
          "NVIDIA driver + NVIDIA Container Toolkit on the host (verified via `nvidia-smi` and `lspci -nnk -d 10de:`).",
          "An NVIDIA GPU with at least 6 GB VRAM (RTX 5090 / 4090 / 3090 / A6000 / L40 all work).",
          "For Blackwell (sm_120) cards: driver 595+ open variant, torch ≥ 2.7 cu128 wheels — handled by the GPU image.",
        ],
      },
      { type: "h", level: 3, text: "1. Drop the weights" },
      {
        type: "code",
        lang: "bash",
        text: "mkdir -p models/lipsync/sadtalker/{checkpoints,gfpgan}\n# from upstream:\ncurl -fL -o models/lipsync/sadtalker/checkpoints/mapping_00109-model.pth.tar \\\n  https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc/mapping_00109-model.pth.tar\ncurl -fL -o models/lipsync/sadtalker/checkpoints/mapping_00229-model.pth.tar \\\n  https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc/mapping_00229-model.pth.tar\ncurl -fL -o models/lipsync/sadtalker/checkpoints/SadTalker_V0.0.2_256.safetensors \\\n  https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc/SadTalker_V0.0.2_256.safetensors\ncurl -fL -o models/lipsync/sadtalker/checkpoints/SadTalker_V0.0.2_512.safetensors \\\n  https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc/SadTalker_V0.0.2_512.safetensors\ncurl -fL -o models/lipsync/sadtalker/gfpgan/GFPGANv1.4.pth \\\n  https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth",
        caption: "Total ~2 GB. License terms apply — review before production use.",
      },
      { type: "h", level: 3, text: "2. Build & start the GPU wrapper" },
      {
        type: "code",
        lang: "bash",
        text: "make docker-sadtalker-build         # ~10 min, ~19 GB image\nmake docker-sadtalker-up            # starts model-sadtalker on profile=sadtalker\nmake docker-sadtalker-smoke         # GET /health → status:ready",
      },
      { type: "h", level: 3, text: "3. Tell the backend about it" },
      {
        type: "code",
        lang: "bash",
        text: "export SADTALKER_BASE_URL=http://aivideo-model-sadtalker-1:8080\n\nBACKEND_PORT=8001 FRONTEND_PORT=3001 POSTGRES_PORT=5433 REDIS_PORT=6380 \\\n  NEXT_PUBLIC_API_BASE_URL=http://localhost:8001 \\\n  SADTALKER_BASE_URL=$SADTALKER_BASE_URL \\\n  docker compose -f docker/compose.dev.yml up -d --no-deps --force-recreate backend",
        caption: "The light backend stays torch-free; everything heavy runs in model-sadtalker.",
      },
      { type: "h", level: 3, text: "4. Verify end-to-end" },
      {
        type: "code",
        lang: "bash",
        text: "curl -fsS http://localhost:8062/health | jq '.status, .details.runtime.torch_cuda_device_name'\n# → \"ready\"  \"NVIDIA GeForce RTX 5090 Laptop GPU\"\n\ncurl -sS -X POST http://localhost:8001/api/v1/video/generate \\\n  -H 'Content-Type: application/json' \\\n  -d '{...job_id, image_artifact_id, audio_artifact_id, provider_id:\"sadtalker\", target_duration_seconds:15}'",
      },
      {
        type: "callout",
        tone: "success",
        title: "Expected timing",
        text: "RTX 5090: ~120 s per 15 s reel at size=256 + GFPGAN. Numbers ≫ 3 min usually mean the GPU is shared with another process; check nvidia-smi.",
      },
      { type: "linkArticle", slug: "video-troubleshoot", label: "If something breaks: SadTalker troubleshooting →" },
    ],
    related: ["video-troubleshoot", "infra-gpu", "infra-docker-profiles"],
  },
  {
    slug: "video-troubleshoot",
    title: "Troubleshooting SadTalker",
    section: "video",
    summary: "Every error code seen during real inference + its fix.",
    keywords: ["sadtalker", "troubleshoot", "error", "cuda", "kernel", "blackwell"],
    body: [
      {
        type: "kv",
        rows: [
          ["status=not_implemented", "Real-inference flags are off. Set SADTALKER_ENABLE_REAL_INFERENCE=true + RUN_REAL_SADTALKER=1, OR set SADTALKER_BASE_URL on the backend to route via the GPU wrapper."],
          ["video_assets_missing", "One of the 5 weight files isn't on disk under SADTALKER_MODELS_ROOT. Re-download as listed in SadTalker setup."],
          ["video_runtime_missing (no torch)", "Backend image is torch-free by design. Use the GPU wrapper service; don't try to install torch in the light backend."],
          ["video_runtime_missing (no sadtalker module)", "GPU image lacks the source clone. Rebuild with `make docker-sadtalker-build`."],
          ["video_gpu_missing", "Inside the GPU container `torch.cuda.is_available()` is False. Check NVIDIA Container Toolkit (`docker run --rm --gpus all nvidia/cuda:12.4.1-runtime-ubuntu22.04 nvidia-smi`)."],
          ["RuntimeError: CUDA error: no kernel image is available", "Your GPU is newer than the torch wheels know about (Blackwell on torch ≤ 2.6 cu124). Rebuild the wrapper with torch 2.7.1 cu128 (default for Phase 10B)."],
          ["AttributeError: module 'numpy' has no attribute 'float'", "SadTalker upstream uses removed numpy aliases. The wrapper Dockerfile patches them automatically; if you forked it, re-apply the sed step."],
          ["ValueError: setting an array element with a sequence", "Same numpy upgrade story for align_img preprocess.py. Wrapper Dockerfile already patches it."],
          ["Permission denied moving MP4", "/storage/artifacts subdirs got created with mismatched uids between backend (uid 1000) and wrapper (uid 10002). One-shot fix: `docker exec -u 0 aivideo-backend-1 chmod -R o+rwX /storage/artifacts`."],
        ],
      },
    ],
    related: ["sadtalker-setup", "error-codes", "infra-gpu"],
  },

  // ===========================================================================
  // SECTION: voice
  // ===========================================================================
  {
    slug: "voice-piper",
    title: "Piper (default TTS)",
    section: "voice",
    summary: "Local Piper TTS — voices on disk, no network.",
    keywords: ["piper", "tts", "voice", "english", "local"],
    body: [
      {
        type: "p",
        text: "Piper is the default TTS engine. CPU-friendly, fast, and never makes a network call. Multiple voices supported — just drop the .onnx + .onnx.json pair under PIPER_MODELS_ROOT.",
      },
      { type: "h", level: 3, text: "Install & enable" },
      {
        type: "code",
        lang: "bash",
        text: "# Inside the backend image — needs a rebuild:\nINSTALL_PIPER=true make docker-light-build\nmake docker-light-up\n\n# Drop voices under models/tts/piper/<voice>/<voice>.onnx + .onnx.json\n# Set in .env:\nPIPER_MODELS_ROOT=/models/tts/piper",
      },
      {
        type: "callout",
        tone: "info",
        text: "If you don't want to rebuild the backend, mount piper at runtime from a sibling agent container — but the easiest path is the rebuild flag.",
      },
    ],
    related: ["voice-f5tts-ro", "inputs-audio"],
  },
  {
    slug: "voice-f5tts-ro",
    title: "F5TTS-Ro (Romanian)",
    section: "voice",
    summary: "Optional Romanian TTS wrapper. CPU-default, GPU-capable.",
    keywords: ["f5tts", "romanian", "tts", "ro", "racai", "voice cloning"],
    body: [
      {
        type: "p",
        text: "F5TTS-Ro is an opt-in wrapper around upstream F5-TTS configured for Romanian. It runs in its own Docker service (profile=tts-ro) so the backend stays torch-free.",
      },
      { type: "h", level: 3, text: "Setup" },
      {
        type: "code",
        lang: "bash",
        text: "# Build + start:\nmake docker-tts-ro-build\nmake docker-tts-ro-up\n\n# Tell the backend:\nexport F5TTS_RO_BASE_URL=http://aivideo-model-tts-ro-1:8080\n\n# Reference voice (operator-supplied):\n# place a WAV at models/tts/f5tts-ro/reference/voice.wav\n# plus the transcript in F5TTS_RO_REFERENCE_TEXT env var",
      },
      {
        type: "p",
        text: "When the wrapper is up, /api/v1/providers/tts shows f5tts_ro with status=ok and the wrapper /health endpoint reports torch + reference audio state.",
      },
    ],
    related: ["voice-piper", "providers-status"],
  },
  {
    slug: "voice-provided-audio",
    title: "Provided audio mode",
    section: "voice",
    summary: "Skip TTS entirely — drive lip-sync from an uploaded WAV.",
    keywords: ["provided", "audio", "skip tts", "upload", "voice mode"],
    body: [
      {
        type: "p",
        text: "When voice_mode=provided_audio, the voice stage validates the uploaded WAV (PCM, mono / stereo, duration in range) and skips synthesis entirely. The lipsync stage uses the provided audio directly.",
      },
      {
        type: "list",
        items: [
          "Upload via /uploads → audio. Note the artifact_id.",
          "Reference it in the job via audio_ref={type:'local_path', path, mime_type:'audio/wav', checksum, consent_confirmed:true, synthetic_or_owned_voice:true}.",
          "synthetic_or_owned_voice is mandatory — the schema rejects unowned voice samples.",
        ],
      },
    ],
    related: ["inputs-audio", "page-uploads"],
  },

  // ===========================================================================
  // SECTION: compliance
  // ===========================================================================
  {
    slug: "compliance-overview",
    title: "Compliance overview",
    section: "compliance",
    summary: "Four gates, one signing key, one event log.",
    keywords: ["compliance", "policy", "gate", "officer", "audit"],
    body: [
      {
        type: "kv",
        caption: "The four gates",
        rows: [
          ["Synthetic-only attestation", "Required at job create + image_ref + audio_ref level."],
          ["Consent attestation", "Required at job create + per-ref. Operator-attested."],
          ["Watermark requirement", "watermark_required=true forces the publisher to embed a visible AI-content marker before publish."],
          ["C2PA requirement", "c2pa_required=true forces the final export to be signed with a C2PA manifest (provenance + revocation list compatible)."],
        ],
      },
      {
        type: "p",
        text: "Every accept / reject lands in /api/v1/jobs/<id>/compliance-events with the decision, reason, and a timestamp. This is the audit trail; it survives job resets.",
      },
    ],
    related: ["synthetic-only", "compliance-watermark-c2pa", "compliance-tokens"],
  },
  {
    slug: "compliance-watermark-c2pa",
    title: "Watermark & C2PA",
    section: "compliance",
    summary: "Visible AI marker + cryptographic provenance manifest.",
    keywords: ["watermark", "c2pa", "provenance", "ai disclosure"],
    body: [
      { type: "h", level: 3, text: "Visible watermark" },
      {
        type: "p",
        text: "When watermark_required=true the publisher overlays a small AI-content badge in the corner of the final MP4. The text is configurable per deploy but cannot be disabled per-job.",
      },
      { type: "h", level: 3, text: "C2PA manifest" },
      {
        type: "p",
        text: "When c2pa_required=true the publisher signs the MP4 with a C2PA manifest containing the producer (this app), the AI disclosure, the upstream providers, and a sha256 of the bytes signed. Compatible viewers (Adobe, BBC, etc.) will display the badge.",
      },
      {
        type: "callout",
        tone: "warn",
        text: "Both flags are sticky-true. The form refuses a PATCH that sets either to false — flip them off only by editing the job in the DB (and don't, unless you mean it).",
      },
    ],
    related: ["compliance-overview", "publisher"],
  },
  {
    slug: "compliance-tokens",
    title: "Compliance tokens (lipsync gate)",
    section: "compliance",
    summary: "Why the lipsync stage refuses without a signed token.",
    keywords: ["token", "hmac", "signing key", "lipsync", "auth"],
    body: [
      {
        type: "p",
        text: "Between the face stage and the lipsync stage, the orchestrator runs pre_lipsync_auth — it mints an HMAC token bound to (job_id, allowed_lipsync_backend, expiry). The lipsync provider verifies that token before invoking any model.",
      },
      {
        type: "p",
        text: "The HMAC secret is COMPLIANCE_SIGNING_KEY, set in .env. Backend + orchestrator + agent containers all need the same value; otherwise the token never verifies and you'll see compliance_token_invalid in stage rejections.",
      },
      {
        type: "code",
        lang: "bash",
        text: "# Single source of truth — set once in .env:\nCOMPLIANCE_SIGNING_KEY=use-a-random-32-byte-secret\n\n# After changing it, restart EVERY agent + backend:\nmake docker-light-down\nmake docker-light-up",
      },
    ],
    related: ["compliance-overview", "stage-rejections"],
  },

  // ===========================================================================
  // SECTION: infra
  // ===========================================================================
  {
    slug: "infra-docker-profiles",
    title: "Docker compose profiles",
    section: "infra",
    summary: "Light, GPU, sadtalker, tts-ro, llm — what each profile starts.",
    keywords: ["docker", "compose", "profile", "stack", "gpu"],
    body: [
      {
        type: "kv",
        rows: [
          ["(default)", "postgres, redis, minio, backend, frontend, orchestrator, agent-* CPU stubs."],
          ["--profile gpu", "Layers compose.gpu.yml: agent-voice / agent-face / agent-lipsync get the CUDA image + GPU reservations. Used by older Dockerfile.cuda."],
          ["--profile sadtalker", "Starts model-sadtalker (Phase 10B GPU wrapper, port 8062)."],
          ["--profile tts-ro", "Starts model-tts-ro (F5TTS-Ro wrapper, port 8061)."],
          ["--profile llm", "Starts model-llm (vLLM-style local LLM)."],
        ],
      },
      {
        type: "p",
        text: "Profiles compose — you can run multiple at once. Common dev combo: default + sadtalker + tts-ro.",
      },
    ],
    related: ["sadtalker-setup", "voice-f5tts-ro", "infra-volumes"],
  },
  {
    slug: "infra-volumes",
    title: "Named volumes",
    section: "infra",
    summary: "What lives where. Never delete by accident.",
    keywords: ["volume", "storage", "postgres", "artifacts", "inputs", "data"],
    body: [
      {
        type: "kv",
        rows: [
          ["aivideo_postgres_data", "Postgres datadir. Holds every job + stage_run + artifact row + compliance event."],
          ["aivideo_redis_data", "Redis AOF. Pub/sub state, optional queue (currently lightly used)."],
          ["aivideo_inputs_data", "Mounted at /storage/inputs in backend + orchestrator. Holds every uploaded WAV / PNG / text."],
          ["aivideo_artifacts_data", "Mounted at /storage/artifacts. Holds every generated artifact (scripts JSON, edit plans JSON, MP4s, etc)."],
        ],
      },
      {
        type: "callout",
        tone: "danger",
        title: "Do NOT run docker compose down -v",
        text: "The -v flag deletes the named volumes. Use `make docker-light-down` or plain `docker compose stop` to preserve data.",
      },
    ],
    related: ["infra-docker-profiles", "page-job-detail"],
  },
  {
    slug: "infra-gpu",
    title: "GPU prerequisites",
    section: "infra",
    summary: "Driver, container toolkit, sm version, common gotchas.",
    keywords: ["gpu", "nvidia", "driver", "cuda", "container toolkit", "blackwell"],
    body: [
      { type: "h", level: 3, text: "Host checklist" },
      {
        type: "list",
        items: [
          "`nvidia-smi` lists at least one device. If it says \"No devices were found\" run `lspci -nnk -d 10de:` to confirm the GPU exists physically — driver might be wrong.",
          "`docker run --rm --gpus all nvidia/cuda:12.4.1-runtime-ubuntu22.04 nvidia-smi` succeeds (NVIDIA Container Toolkit is registered).",
          "`prime-select query` says `on-demand` or `nvidia` on Optimus laptops; `intel` means the dGPU stays off.",
        ],
      },
      { type: "h", level: 3, text: "Open vs closed driver (Blackwell)" },
      {
        type: "p",
        text: "RTX 50-series Blackwell cards require the open-kernel-module driver variant (e.g. nvidia-driver-595-open). The closed-source variant does not bind the device on this generation.",
      },
      { type: "h", level: 3, text: "Common gotchas" },
      {
        type: "list",
        items: [
          "Optimus laptops: dGPU is suspended until a process targets it. `cat /sys/bus/pci/devices/*/power/runtime_status` shows `suspended` — that's normal.",
          "Multiple GPUs: NVIDIA_VISIBLE_DEVICES=0 pins to the first device; set to `all` to expose every device.",
          "Power profile P8 / 9 W idle is normal at rest.",
        ],
      },
    ],
    related: ["sadtalker-setup", "video-troubleshoot"],
  },

  // ===========================================================================
  // SECTION: troubleshooting
  // ===========================================================================
  {
    slug: "troubleshooting-frontend",
    title: "Frontend troubleshooting",
    section: "troubleshooting",
    summary: "Blank page, stuck polling, backend unreachable, cache issues.",
    keywords: ["frontend", "blank", "polling", "stuck", "next js", "cache"],
    body: [
      {
        type: "kv",
        rows: [
          ["Blank page after deploy", "Hard refresh (Ctrl-Shift-R). The service worker / Next cache may pin old chunks."],
          ["\"Backend unreachable\"", "Check the badge: NEXT_PUBLIC_API_BASE_URL points at the backend port. CORS errors show in browser devtools — backend must allow the frontend origin."],
          ["Right sidebar stuck loading", "Open Logs tab; the LogsPanel reports the failing API call. Usually a /api/v1/providers/* 502 while a heavy provider boots."],
          ["Job page polls forever", "Backend returned an unexpected payload shape. Logs panel surfaces the parse error; check backend logs with `docker compose logs backend`."],
        ],
      },
    ],
    related: ["page-job-detail", "logs-panel"],
  },
  {
    slug: "troubleshooting-faq",
    title: "FAQ",
    section: "troubleshooting",
    summary: "Common questions, terse answers.",
    keywords: ["faq", "frequent", "questions", "answers"],
    body: [
      {
        type: "kv",
        rows: [
          ["Can I use a real face?", "No. The pipeline refuses at schema + compliance + provider layers. See Synthetic-only rule."],
          ["Why is my MP4 only 512×512?", "SadTalker default. Pass size=512 in the wrapper request (or via the editor stage) for a 512² output. Higher res requires custom training."],
          ["How big is the SadTalker image?", "~19 GB. Most of it is torch + cuDNN + the cu128 wheel."],
          ["Where do generated MP4s live?", "Inside the named volume aivideo_artifacts_data, under /storage/artifacts/video/<job_id>/. Download via the dashboard or API."],
          ["Can I run two GPU pipelines at once?", "Yes — model-sadtalker and model-tts-ro both reserve 1 GPU; if your host has 2 GPUs, set NVIDIA_VISIBLE_DEVICES per service."],
          ["What happens if I delete a model weight?", "The provider's healthcheck flips to assets_missing the next time the dashboard polls. Jobs that haven't reached lipsync stay queued; running ones get rejected with video_assets_missing."],
        ],
      },
    ],
    related: ["synthetic-only", "sadtalker-setup", "infra-volumes"],
  },

  // ===========================================================================
  // SECTION: reference
  // ===========================================================================
  {
    slug: "error-codes",
    title: "Error codes reference",
    section: "reference",
    summary: "Every error_code returned by the API.",
    keywords: ["error", "codes", "reference", "list"],
    body: [
      { type: "h", level: 3, text: "Schema-layer errors (HTTP 422)" },
      {
        type: "kv",
        rows: [
          ["synthetic_person_confirmed_required", "image_ref carries a real-person attestation toggle off."],
          ["consent_confirmed_required", "image_ref / audio_ref / job-level consent not asserted."],
          ["wrong_image_artifact_type", "Sent a non-image artifact in image_artifact_id."],
          ["wrong_audio_artifact_type", "Same for audio."],
          ["unknown_provider", "provider_id not in the registry."],
        ],
      },
      { type: "h", level: 3, text: "Provider readiness errors (HTTP 200, structured)" },
      {
        type: "kv",
        rows: [
          ["provider_not_implemented", "Default placeholder state."],
          ["tts_provider_not_configured", "Backend points at a TTS provider that needs an env var (PIPER_MODELS_ROOT / F5TTS_RO_BASE_URL)."],
          ["tts_runtime_missing", "TTS library not installed in this image."],
          ["tts_assets_missing", "Weights / voice files not on disk."],
          ["tts_generation_failed", "Synthesis ran but the WAV failed validation. Partial files are scrubbed."],
          ["video_provider_not_configured", "SADTALKER_MODELS_ROOT unset."],
          ["video_runtime_missing", "torch / sadtalker not importable."],
          ["video_assets_missing", "Weights missing under the configured root."],
          ["video_gpu_missing", "torch present but no visible CUDA device."],
          ["video_generation_failed", "Inference attempted; raised. See message for the wrapper's tail."],
        ],
      },
      { type: "h", level: 3, text: "Stage rejection codes (compliance_events)" },
      {
        type: "kv",
        rows: [
          ["compliance_attestation_missing", "synthetic_person_confirmed / consent_confirmed off at job level."],
          ["compliance_token_invalid", "lipsync token failed HMAC verification (signing key mismatch, expired, or wrong allowed_lipsync_backend)."],
          ["upstream_voice_missing", "lipsync called without a voice artifact attached. Earlier stage failed silently."],
          ["upstream_face_missing", "Same for the face stage."],
          ["qc_lipsync_confidence_low", "QC ran; lip-sync metric below threshold."],
          ["qc_disclosure_missing", "QC ran; the AI-content disclosure didn't make it into the final MP4."],
        ],
      },
    ],
    related: ["stage-rejections", "video-troubleshoot"],
  },
  {
    slug: "keyboard-shortcuts",
    title: "Keyboard shortcuts",
    section: "reference",
    summary: "All registered shortcuts.",
    keywords: ["keyboard", "shortcut", "hotkey", "kbd"],
    body: [
      {
        type: "kv",
        rows: [
          ["?", "Open Help (this overlay) from any page."],
          ["Esc", "Close Help (or any open modal)."],
          ["/", "Focus Help search when the overlay is open."],
          ["g then j", "Go to Jobs list (when not typing in an input)."],
          ["g then n", "Go to New job."],
          ["g then u", "Go to Uploads."],
          ["g then s", "Go to Settings."],
          ["[ / ]", "Collapse / expand the right sidebar."],
        ],
      },
      {
        type: "p",
        text: "Shortcuts are global except where a text input has focus.",
      },
    ],
    related: ["page-dashboard"],
  },
  {
    slug: "api-reference",
    title: "API summary",
    section: "reference",
    summary: "The endpoints the dashboard actually uses.",
    keywords: ["api", "endpoints", "rest", "reference"],
    body: [
      {
        type: "kv",
        rows: [
          ["GET /healthz", "Liveness. Returns 200 ok when DB + Redis are reachable."],
          ["GET /api/v1/system/status", "Aggregate readiness (DB / Redis / settings / time)."],
          ["GET /api/v1/providers/{category}", "List providers in a category with live readiness notes."],
          ["GET /api/v1/jobs", "Paginated job list."],
          ["POST /api/v1/jobs", "Create a job."],
          ["GET /api/v1/jobs/{id}", "Full job detail."],
          ["PATCH /api/v1/jobs/{id}", "Edit a non-terminal job."],
          ["POST /api/v1/jobs/{id}/cancel", "Terminal-cancel a job."],
          ["POST /api/v1/jobs/{id}/retry", "Retry from an earlier stage."],
          ["GET /api/v1/jobs/{id}/artifacts", "Artifact list for a job."],
          ["GET /api/v1/jobs/{id}/timeline", "Stage runs (status + duration + reason)."],
          ["GET /api/v1/jobs/{id}/compliance-events", "Audit trail."],
          ["GET /api/v1/jobs/{id}/qc-report", "QC decision + metrics."],
          ["GET /api/v1/jobs/{id}/final-export", "Publisher bundle."],
          ["POST /api/v1/uploads/image", "Multipart image upload."],
          ["POST /api/v1/uploads/audio", "Multipart audio upload."],
          ["POST /api/v1/tts/generate", "Direct TTS preview (Piper / F5TTS-Ro)."],
          ["POST /api/v1/video/generate", "Direct video generation (SadTalker)."],
          ["GET /api/v1/artifacts/{id}/content", "Download artifact bytes. ?download=true sets Content-Disposition attachment."],
        ],
      },
      {
        type: "p",
        text: "Full machine-readable spec at GET /openapi.json (Swagger UI at /docs when DEBUG=true).",
      },
    ],
    related: ["error-codes"],
  },
  {
    slug: "glossary",
    title: "Glossary",
    section: "reference",
    summary: "Quick definitions, A–Z.",
    keywords: ["glossary", "terms", "dictionary"],
    body: [
      {
        type: "kv",
        rows: [
          ["Artifact", "A typed output of a stage. Has sha256, size, mime, and either inline JSON or a local path."],
          ["Backend (light)", "The default API container — torch-free, fast to start, never runs ML."],
          ["C2PA", "Coalition for Content Provenance and Authenticity manifest format. Embeds origin metadata into the MP4."],
          ["Compliance event", "An accept / reject record in compliance_events. Audit-only."],
          ["DAG", "Directed acyclic graph — the fixed pipeline of stages."],
          ["GFPGAN", "Face-restoration model (TencentARC). Optional post-process for SadTalker."],
          ["MuseTalk", "Newer lip-sync model from TMElyralab. Wiring deferred."],
          ["Provider", "A pluggable backend (a Python class) wired into a stage."],
          ["SadTalker", "Default lip-sync model from OpenTalker. Phase 10B integration."],
          ["Stage", "One node in the DAG."],
          ["Wav2Lip", "Older lip-sync model — fast fallback when SadTalker can't crop a face."],
        ],
      },
    ],
    related: ["core-concepts", "job-lifecycle"],
  },
];

export const HELP_DEFAULT_SLUG = "welcome";

export function getArticleBySlug(slug: string): HelpArticle | undefined {
  return HELP_ARTICLES.find((a) => a.slug === slug);
}

export function getArticlesBySection(sectionId: string): readonly HelpArticle[] {
  return HELP_ARTICLES.filter((a) => a.section === sectionId);
}
