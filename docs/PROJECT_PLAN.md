# P1.AIVideo — Technical Project Plan

Approved scope as of 2026-05-12. This document is the source of truth for the v1 plan; all subordinate docs link back here.

---

## 1. Overall Project Objective

Build a self-hosted, Docker-based, multi-agent pipeline that produces short (15–60s) vertical reel videos featuring a **synthetic, fully AI-generated white Caucasian human** performing lip-synced speech driven by a text prompt or script.

The system is:

- **Modular** — each pipeline stage runs in its own container.
- **Agent-orchestrated** — specialized agents collaborate on a job.
- **Compliance-first** — synthetic persona only; visible + metadata AI disclosure on every output; no real-person likeness or voice.
- **Reproducible** — given the same seed + prompt + config, output is stable enough for QA.

**Non-goals:** real-person impersonation, voice cloning of real individuals, face-swap onto real footage, political/electoral content, adult content, medical/financial advice presented as authoritative.

---

## 2. Functional Requirements

| ID | Requirement |
|---|---|
| F-01 | Accept a text brief (topic, tone, duration, language) via REST API and frontend UI. |
| F-02 | Generate a script (hook + body + CTA) under the requested duration. |
| F-03 | Synthesize speech in a chosen synthetic voice profile (no cloning of real voices). |
| F-04 | Generate or load a synthetic human portrait/avatar (white Caucasian, configurable age range, neutral identity). |
| F-05 | Produce a talking-head video with accurate phoneme-level lip-sync. |
| F-06 | Compose final vertical 1080×1920 reel: subtitles, B-roll/background, music bed, AI disclosure overlay. |
| F-07 | Embed C2PA / metadata disclosure marking the output as AI-generated. |
| F-08 | Run automated QC (face stability, sync offset, audio levels, banned-content scan). |
| F-09 | Persist job artifacts (script, voice, frames, final video) under a job UUID. |
| F-10 | Expose job status, logs, and previews in the frontend. |
| F-11 | Allow rejection/regeneration of any single stage without rerunning the full pipeline. |
| F-12 | Provide an audit log of every prompt, model version, seed, and operator action. |

---

## 3. Non-Functional Requirements

- **Performance:** end-to-end ≤ 10 min on a single RTX 4090 / L4-class GPU for a 30s reel.
- **Reliability:** idempotent stages; resumable on container restart.
- **Observability:** structured JSON logs, Prometheus metrics, per-stage timings, Grafana dashboard.
- **Portability:** Linux host with NVIDIA Container Toolkit; no host deps beyond Docker + drivers.
- **Scalability:** horizontal scaling of stateless stages via Redis queue; GPU stages bound by available devices.
- **Security:** no inbound traffic except via reverse proxy; secrets via Docker secrets / `.env` excluded from VCS.
- **Maintainability:** each agent ≤ 500 LOC of orchestration code; models pinned by hash.
- **Cost ceiling:** zero external API cost in default config; optional paid backends behind feature flags.

---

## 4. Technical Architecture

```
┌────────────┐    ┌──────────────┐    ┌────────────────────┐
│  Frontend  │◄──►│  Backend API │◄──►│  Job Queue (Redis) │
│  (Next.js) │    │  (FastAPI)   │    └─────────┬──────────┘
└────────────┘    └──────┬───────┘              │
                         │                       ▼
                         │            ┌──────────────────────┐
                         │            │  Orchestrator Agent  │
                         │            └──────────┬───────────┘
                         ▼                       ▼
                  ┌──────────────┐   ┌─────────────────────────────┐
                  │   Postgres   │   │ Specialist Agents (workers) │
                  │   + MinIO    │   │  Script | Voice | Face |    │
                  └──────────────┘   │  LipSync| Editor| QC | Pub  │
                                     └──────────────┬──────────────┘
                                                    ▼
                                          ┌──────────────────┐
                                          │ Model Servers    │
                                          │ (vLLM, ComfyUI,  │
                                          │  provider procs) │
                                          └──────────────────┘
```

- **Frontend:** Next.js + Tailwind; REST + WebSocket for live progress.
- **Backend:** FastAPI; JWT auth, RBAC, job CRUD.
- **Queue:** Redis Streams.
- **DB:** Postgres for jobs/audit/users; MinIO (S3-compatible) for artifacts.
- **Orchestrator:** LangGraph DAG; one job → DAG of agent tasks.
- **Specialist agents:** each is a worker container subscribing to its queue topic.
- **Model servers:** hot-loaded GPU services so agents don't reload weights per job.

See [architecture/overview.md](architecture/overview.md), [architecture/data-flow.md](architecture/data-flow.md), [architecture/agents.md](architecture/agents.md), and [architecture/lipsync-adapter.md](architecture/lipsync-adapter.md).

---

## 5. Docker Architecture

One `docker/compose.dev.yml` plus a `compose.gpu.yml` overlay; `compose.prod.yml` for production. Future: Helm chart for k8s.

| Service | Image base | GPU | Purpose |
|---|---|---|---|
| `frontend` | node:20-alpine | no | Next.js UI |
| `backend` | python:3.11-slim | no | FastAPI |
| `postgres` | postgres:16 | no | Metadata |
| `redis` | redis:7 | no | Queue + cache |
| `minio` | minio/minio | no | Object storage |
| `orchestrator` | python:3.11 | no | DAG runner |
| `agent-script` | python:3.11 | optional | LLM client |
| `agent-voice` | nvidia/cuda:12.4 | yes | TTS |
| `agent-face` | nvidia/cuda:12.4 | yes | SDXL/Flux portrait gen |
| `agent-lipsync` | nvidia/cuda:12.4 | yes | SadTalker (v1) via adapter |
| `agent-editor` | python:3.11 + ffmpeg | no | Compositing |
| `agent-qc` | python:3.11 | optional | Validation checks |
| `agent-publisher` | python:3.11 | no | Metadata + C2PA + export |
| `agent-compliance` | python:3.11 | no | Policy enforcement |
| `model-llm` | vllm/vllm-openai | yes | Local LLM serve |
| `prometheus` | prom/prometheus | no | Metrics |
| `grafana` | grafana/grafana | no | Dashboards |
| `traefik` | traefik:v3 | no | Reverse proxy + TLS |

Conventions: multi-stage builds, non-root users, healthchecks, named volumes for models/storage, GPU access via `deploy.resources.reservations.devices`.

---

## 6. Folder Structure

See [README.md](../README.md). Top-level: `docs/`, `docker/`, `backend/`, `frontend/`, `agents/`, `pipelines/`, `models/`, `assets/`, `scripts/`, `storage/`, `tests/`, `configs/`.

---

## 7. Data Flow

```
User brief
   │
   ▼
[Backend] creates Job(uuid, brief, policy_check=pending)
   │
   ▼
[Policy Gate] keyword + classifier check → reject or proceed
   │
   ▼
[Orchestrator] enqueues stages per pipeline DAG
   │
   ├─► [Scriptwriter] → script.json
   ├─► [Voice]        → narration.wav + phonemes.json
   ├─► [Face]         → portrait.png (+ alt seeds)
   ├─► [LipSync]      → talking_head.mp4
   ├─► [Editor]       → reel_draft.mp4 (subs, music, overlays)
   ├─► [QC]           → qc_report.json
   └─► [Publisher]    → reel_final.mp4 + sidecar.json (C2PA, hashes)
   │
   ▼
Artifacts in MinIO under jobs/{uuid}/...; metadata in Postgres
```

Every stage writes inputs/outputs to MinIO and a row to `stage_runs` recording model + seed + hash. See [architecture/data-flow.md](architecture/data-flow.md).

---

## 8. AI Pipeline Stages

1. **Intake & Policy Gate** — schema-validate brief; run banned-topic classifier; require `synthetic_person=true`.
2. **Script Generation** — LLM produces hook/body/CTA, target duration, SSML hints.
3. **Voice Synthesis** — synthetic-voice TTS; phoneme/viseme timestamps emitted.
4. **Persona/Face Generation** — SDXL + persona LoRA on licensed synthetic dataset; neutral frontal still + optional turn-head frames.
5. **Lip-Sync Animation** — driven via adapter; default SadTalker; output 25–30 fps talking-head clip.
6. **Background & B-roll** — licensed/synthetic library or generated via image-to-video.
7. **Composition & Subtitling** — ffmpeg + MoviePy; vertical 1080×1920; subtitle burn-in; music bed ducking; AI-disclosure overlay; end card.
8. **Quality Control** — face stability, lip-sync confidence, audio LUFS, banned-content rescan, OCR on overlays.
9. **Publisher / Disclosure** — embed C2PA manifest, EXIF/XMP `AI-generated=true`, perceptual hash, sign, audit.

---

## 9. Agent / Team Organigram

```
                       ┌──────────────────────────┐
                       │   Orchestrator Agent     │
                       └────────────┬─────────────┘
              ┌────────────┬────────┼────────┬────────────┬────────────┐
              ▼            ▼        ▼        ▼            ▼            ▼
        Scriptwriter   Voice     Face    LipSync       Editor         QC
                                                                       │
                                                                       ▼
                                                                  Publisher
                       (Compliance Officer agent observes every stage)
```

See [architecture/agents.md](architecture/agents.md) for full responsibility sheets.

---

## 10. Agent Responsibility Sheets

(Summary; full detail in [architecture/agents.md](architecture/agents.md).)

- **Orchestrator** — DAG runner, retries, budget enforcement.
- **Scriptwriter** — hook-driven, duration-bounded script in target language/tone.
- **Voice** — synthetic-voice narration with phoneme timestamps; cloning paths stripped.
- **Face** — synthetic Caucasian portrait per persona spec; celebrity-NN guard at output.
- **LipSync** — phoneme-accurate animation via adapter (`LIPSYNC_BACKEND`); see [architecture/lipsync-adapter.md](architecture/lipsync-adapter.md).
- **Editor** — final reel: subs, B-roll, music, branding, disclosure overlay.
- **QC** — structured pass/fail with remediation requests.
- **Publisher** — finalize, sign (C2PA), label (XMP), persist.
- **Compliance Officer** — cross-cutting policy enforcement; issues per-job `compliance_token`.

---

## 11. Required Open-Source Models / Tools

- **LLM (script):** Llama-3.1-8B-Instruct or Qwen2.5-7B-Instruct via vLLM.
- **TTS:** Piper (default) or Coqui XTTS-v2 (synthetic voices only — cloning input path disabled).
- **Portrait gen:** SDXL base + a persona LoRA trained on licensed synthetic-face data.
- **Image-to-video / B-roll:** Stable Video Diffusion, AnimateDiff.
- **Lip-sync:** SadTalker (v1 default), MuseTalk (v2), Wav2Lip + GFPGAN (fallback) — all behind the LipSync adapter.
- **Speech alignment / subs:** WhisperX, faster-whisper.
- **Upscaling:** Real-ESRGAN, CodeFormer.
- **Audio:** ffmpeg, sox, pyloudnorm.
- **Compositing:** MoviePy, ffmpeg filtergraphs.
- **Safety/NSFW:** Compvis safety checker, NudeNet.
- **Identity guard:** CLIP NN against a public-figures embedding index (negative filter; used to reject only).
- **Disclosure / provenance:** c2pa-rs / c2patool, ExifTool.
- **Orchestration:** LangGraph; Arq/Celery for workers.
- **Serving:** vLLM, ComfyUI (headless), Triton (optional).

License audit per model lives in [`models/MODEL_CARDS.md`](../models/MODEL_CARDS.md).

---

## 12. Optional Paid Services (all OFF by default)

- LLM fallback: Anthropic Claude API, OpenAI.
- TTS fallback: ElevenLabs (synthetic voices only), Azure Neural TTS.
- Music: Mubert, Soundraw, pre-licensed libraries.
- Stock B-roll: Pexels/Pixabay, Storyblocks.
- Moderation: OpenAI Moderation, Perspective API.
- Publishing: TikTok/Instagram/YouTube APIs (future).
- C2PA signing identity: org-issued or paid-CA cert.

Each is behind an adapter and disabled per-environment unless explicitly enabled.

---

## 13. Hardware Requirements

**Minimum dev:** 8c/16t CPU, 32 GB RAM, 1 TB NVMe, 1× 16 GB GPU, Ubuntu 22.04/24.04, NVIDIA driver ≥ 550.

**Recommended:** 16c CPU, 64 GB RAM, 2 TB NVMe + 4 TB HDD, 1× RTX 4090 (24 GB) or L40S.

**Production:** 2× RTX 4090 or 1× H100/L40S, 128 GB RAM, 4 TB NVMe RAID1, 1 Gbps uplink.

---

## 14. GPU Requirements (peak VRAM per stage)

| Stage | Model | VRAM | Notes |
|---|---|---|---|
| LLM (script) | Llama-3.1-8B Q4 | ~6 GB | CPU fallback possible |
| TTS | XTTS-v2 | ~4 GB | Piper is CPU-friendly |
| Face gen | SDXL + LoRA | ~10 GB | fp16 |
| Image-to-video | SVD | ~12 GB | optional |
| Lip-sync | SadTalker | ~6 GB | v1 default |
| Lip-sync HQ | MuseTalk | ~10 GB | v2 roadmap |
| Restoration | GFPGAN/Real-ESRGAN | ~4 GB | |
| Whisper align | large-v3 | ~6 GB | |

Stages are scheduled sequentially per GPU; multi-GPU hosts can parallelize Face + Voice.

---

## 15. Security & Privacy Rules

- Only Traefik exposed publicly (TLS); services on internal Docker network.
- JWT + refresh; RBAC `admin` / `operator` / `viewer`.
- Secrets via Docker secrets / `.env` (gitignored).
- No user-uploaded photos of real people by default. BYO-likeness is **disabled in v1**; future enablement requires a consent module.
- MinIO encryption-at-rest; per-tenant bucket policies.
- TLS 1.3 only; HSTS.
- Prompts/outputs logged; PII redaction before log shipping.
- Retention: artifacts auto-deleted after `JOB_ARTIFACT_TTL_DAYS` (default 30); audit log retained 1 year.
- Containers: non-root, read-only rootfs where possible, dropped capabilities, no `--privileged`.
- Supply chain: pinned image digests; SBOM via Syft; Trivy in CI.
- Model integrity: SHA256 verification on download.

---

## 16. Legal & Ethical Safeguards

- **Synthetic-only persona** with celebrity-NN guard rejecting matches above threshold.
- **No real-voice cloning;** cloning code paths stripped at build time.
- **Mandatory disclosure:**
  - Visible burned-in "AI-generated" overlay (min 4% of frame height).
  - C2PA manifest in the MP4 declaring AI generation, model versions, producer identity.
  - XMP/EXIF `XMP-dc:Source="AI-generated"`.
- **Prohibited use list:** political/electoral, identity fraud, medical/legal/financial advice presented as authoritative, NSFW, hate speech, harassment, minors-in-likeness, real-person impersonation.
- **Consent module (future):** if BYO-likeness is ever enabled — requires signed consent + liveness check + per-job revocation.
- **License tracking:** `assets/LICENSES.md`, `models/MODEL_CARDS.md`.
- **Right-to-deletion:** API endpoint purges a job and derivatives, incl. backups within SLA.
- **Jurisdictional notes:** documented in [compliance/policy.md](compliance/policy.md) (EU AI Act, US state-level deepfake laws, election-period restrictions).
- **Audit trail:** append-only `audit_log` table; every model call recorded with prompt hash, seed, model digest, operator id.

---

## 17. Output Validation Workflow

```
reel_draft.mp4
   │
   ▼
[A] Technical    container/codec, resolution, fps, duration, LUFS, true-peak
[B] Visual       face detected ≥ 95% frames, stability, NSFW=0
[C] Sync         SyncNet ≥ threshold, sub-to-audio < 80 ms drift
[D] Content      re-transcribe → diff vs script; rescan with policy classifier; OCR overlays
[E] Identity     sample N frames → CLIP NN vs public-figures index; reject if ≥ threshold
[F] Provenance   C2PA manifest verifies; perceptual hash recorded
   │
   ▼
 PASS → Publisher;  FAIL → structured remediation request upstream
```

Two consecutive failures escalate to a human review queue.

---

## 18. Development Roadmap

- **Phase 0 — Foundations (Wk 1):** repo scaffolding (this), Docker base images, CI (lint/scan/build), license docs.
- **Phase 1 — Vertical slice (Wks 2–3):** backend CRUD, queue, MinIO, Postgres; minimal Script → Voice → static portrait → Wav2Lip → ffmpeg compose; CLI run.
- **Phase 2 — Multi-agent (Wks 4–5):** LangGraph DAG, retries, per-stage configs; Compliance Officer + policy classifier.
- **Phase 3 — Quality (Wks 6–7):** SDXL + persona LoRA, SadTalker as default adapter impl, GFPGAN restoration, WhisperX subs; music + B-roll.
- **Phase 4 — UX (Wks 8–9):** Next.js dashboard, job form, live progress, regenerate-stage.
- **Phase 5 — Compliance & provenance (Wk 10):** C2PA signing, visible overlay, celebrity-match guard, audit log UI.
- **Phase 6 — Validation & hardening (Wks 11–12):** full QC agent, e2e tests, Grafana dashboards, load test, security review.
- **Phase 7 — v1 release (Wk 13):** tagged release, runbooks, model cards, threat model doc.

---

## 19. Testing Strategy

- **Unit:** per-agent pure-function logic, prompt builders, schema validators.
- **Contract:** every agent's I/O JSON validated against Pydantic schemas; CI fails on drift.
- **Golden-file:** deterministic stages with fixed seeds.
- **Integration:** `compose.test.yml` with mock model servers; 10s reel end-to-end.
- **GPU smoke:** nightly real 15s reel; artifacts + metrics uploaded.
- **Policy tests:** corpus of ~200 briefs; precision/recall of the policy gate tracked.
- **Identity-guard tests:** synthetic faces never trigger; curated celebrity-photo set always triggers.
- **Compliance tests:** every e2e output asserted to carry overlay + valid C2PA + XMP AI-flag.
- **Load tests:** k6 against backend; concurrent jobs vs GPU saturation.
- **Security:** Trivy, Bandit, Gitleaks, OWASP ZAP baseline.

---

## 20. Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Synthetic face resembles a real person | Medium | High | Celebrity-NN guard at QC; reject; manual queue. |
| Misuse for deepfakes / impersonation | Medium | Critical | No real-image input path; consent module disabled v1; ToS + policy classifier; audit log. |
| Voice cloning misuse | Medium | Critical | Cloning code paths stripped at build; only synthetic voice profiles shipped. |
| Output lacks disclosure | Low | High | Publisher refuses to emit without overlay+manifest; QC verifies. |
| Model license violation | Medium | High | Model card review gate in CI; license whitelist. |
| GPU OOM on long jobs | Medium | Medium | Per-stage VRAM budget; tiled inference; lower-VRAM fallback model. |
| Non-determinism breaks reproducibility | Medium | Medium | Pin seeds, model digests, container digests; record in `stage_runs`. |
| Storage growth | High | Medium | TTL purge; tiered storage; content-hash dedup. |
| Prompt injection via brief | Medium | Medium | Strict brief schema; LLM system-prompt isolation; output validator. |
| Supply-chain compromise of model | Low | High | SHA256 pinning; Sigstore where available; internal mirror. |
| Regulatory change | High | Medium | Compliance doc kept current; feature flags to tighten labeling/retention. |
| Bias from single-persona system | High (by spec) | Medium | Documented in model card; not marketed as a general human-generation tool. |
