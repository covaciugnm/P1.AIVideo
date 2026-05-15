# Video Providers — Phase 7A Comparison & First-Provider Recommendation

This document compares the candidate video providers that already exist
in the P1.AIVideo catalog and recommends exactly one to promote first
in Phase 7B. The catalog itself is metadata-only today: every entry
returns `not_implemented` from `/api/v1/video/generate`.

The four lip-sync placeholders + two transport stubs are pinned by
`tests/integration/test_phase7a_gpu_planning.py`. They are:

- `sadtalker` (default v1)
- `musetalk` (v2)
- `wav2lip` (fallback)
- `liveportrait` (research)
- `local_http_video` (operator-run HTTP worker, transport stub)
- `external_video_api` (external API, transport stub)

## 1. Catalog metadata cheat-sheet

```bash
curl -s http://localhost:8000/api/v1/providers/video-generators | jq
```

| provider_id | local_or_external | requires_gpu | requires_model_files | status |
|---|---|---|---|---|
| sadtalker | local | true | true | not_implemented |
| musetalk | local | true | true | not_implemented |
| wav2lip | local | true | true | not_implemented |
| liveportrait | local | true | true | not_implemented |
| local_http_video | local | false | false | not_implemented |
| external_video_api | external | false | false | not_implemented |

The two non-GPU rows are transport stubs — they assume the operator
already runs a worker / API somewhere. They don't change the
host-integration story; they only change *where* the inference happens.

## 2. Side-by-side comparison

> Everything below is design intent, not benchmark data — we have not
> run any of these in this repo. Numbers come from each project's
> README + community reports as of early 2026.

| Property | SadTalker v1 | MuseTalk v2 | Wav2Lip | LivePortrait |
|---|---|---|---|---|
| Repo | OpenTalker/SadTalker | TMElyralab/MuseTalk | Rudrabha/Wav2Lip | KwaiVGI/LivePortrait |
| Lip-sync quality (subjective) | Good | Very good (mouth-only) | Acceptable, fast | Very good (full face) |
| Identity preservation | Strong | Strong | OK | Strong |
| Driving signal | Audio → motion field | Audio → mouth crop | Audio → mouth crop | Driving video / audio |
| VRAM (single image, ≤512 px) | ~6–8 GB | ~6–8 GB | ~2–4 GB | ~12–16 GB |
| Inference speed (≤512 px, RTX A4000-class) | ~1× real-time | ~1.5–2× real-time | ~3–5× real-time | < 1× real-time |
| Output resolution sweet spot | 512² | 256² / 512² | 96² mouth → composited | 512² |
| Weight licence | MIT (code) + research-use weights | MIT (code) + research-use weights | Custom non-commercial | Apache 2.0 (code), separate weight terms |
| Maturity in our pipeline | Pinned as default v1 since Phase 0 | Pinned as v2 since Phase 0 | Pinned as fallback | Phase 6D placeholder, deferred |
| Dependency footprint | torch + safetensors + opencv + gfpgan | torch + diffusers + opencv | torch + opencv | torch + diffusers + xformers |
| Output container | MP4 (H.264) | MP4 (H.264) | MP4 (H.264) | MP4 (H.264) |
| Synthetic-person fit (our use case) | ✅ designed for single still | ✅ ditto | ⚠️ mouth-only — works but visibly cropped | ✅ ditto |
| Compliance fit | Watermark + C2PA post-pass | Same | Same | Same |
| Operator complexity | Medium (one weight bundle) | Medium-high (diffusers weights) | Low (small model) | High (research code, fast-moving) |

### Local-HTTP and external-API stubs

`local_http_video` and `external_video_api` aren't models — they're
transports. They imagine that:

- `local_http_video` — the operator runs their own worker (e.g., a Comfy
  graph, or a wrapped SadTalker on a workstation). The backend POSTs
  job inputs over HTTP, receives an MP4 URI. Provider-adapter code
  lives in the backend, **no GPU dep on the backend host**, and the
  worker is the operator's problem.
- `external_video_api` — a SaaS like Pika / Runway / D-ID. Requires API
  key, requires network egress, model weights stay vendor-side.

Promoting either of these in Phase 7B would unblock real MP4 output
*without* bringing a GPU into the default stack — at the cost of either
operator burden (local_http) or vendor lock-in + compliance review
(external_video_api).

## 3. Recommendation for Phase 7B

**Recommended next step: SadTalker adapter hardening — no real inference
yet.**

Rationale:

1. **Lowest gradient from current state.** SadTalker is already the
   pinned `default v1` provider. Promoting it doesn't introduce a new
   catalog entry; it just changes its status from `not_implemented` to
   `available` once the adapter is real.
2. **VRAM fits the smallest plausible host** (RTX 3060 / A2000 / T4 /
   A4000) at 512² output. We don't lock the operator into a 24 GB card.
3. **Synthetic-person workflow alignment.** SadTalker is *designed* for
   "still portrait + audio → talking-head video". That matches our
   compliance posture (single still image, no real-person video clips
   in the pipeline).
4. **Dependency hygiene is manageable.** torch + safetensors + opencv +
   gfpgan is heavy but bounded — much smaller than the diffusers stack
   MuseTalk would drag in.
5. **Mirrors the Phase 5A pattern.** Phase 5A hardened the Piper TTS
   adapter (env-driven, no auto-download, categorised 503s) before any
   real synthesis. We do the same here: harden the SadTalker provider
   adapter (asset checks, error codes, GPU presence detection) without
   yet running real `torch.cuda` inference. Real inference becomes
   Phase 7C / 7D once the operator surface is solid.

Concretely, Phase 7B should:

- Add `agents.lipsync.providers.sadtalker.provider.SadTalkerProvider`
  with `inspect_assets()` + a `generate()` method that **stays gated
  behind `RUN_REAL_SADTALKER=1`** and otherwise returns the existing
  `not_implemented` shape.
- Add categorised 503s in `/api/v1/video/generate`:
  `video_runtime_missing` (no torch in image), `video_assets_missing`
  (no SadTalker weights under `${SADTALKER_MODELS_ROOT}`),
  `video_gpu_missing` (no CUDA device visible),
  `video_provider_not_configured` (env mis-set),
  `video_generation_failed` (exception during inference).
- Add a `sadtalker-runtime.md` runbook mirroring `piper-runtime.md`'s
  shape: prerequisites, env vars, weight-download recipe (operator
  runs it; we **do not auto-download**), how to enable, how to disable.
- Build the GPU image (`Dockerfile.cuda` + `agents.lipsync` extras)
  only inside an explicit `make docker-gpu-build` target — never as
  part of `make docker-light-build`.

### Alternatives if SadTalker is blocked

| Blocker | Better next step | Why |
|---|---|---|
| No GPU host available at all | `local_http_video` adapter hardening | Lets us write the same 503-categorised adapter without GPU in our stack — operator brings their own worker. |
| Compliance demands no local model weights | `external_video_api` adapter hardening | Weights stay vendor-side; we only design the request/response surface + redact secrets. |
| VRAM ≤ 4 GB | Wav2Lip adapter hardening | Smallest footprint, fastest; accept the mouth-crop quality hit. |
| Research-quality bar required | LivePortrait | But: requires more VRAM and a fast-moving upstream — defer until SadTalker is stable. |

We do **not** recommend jumping to MuseTalk first: it pulls in the full
diffusers stack, which is a much larger commitment to the image budget
than SadTalker. MuseTalk is the natural Phase 7E choice once SadTalker
is shipped and we have a real GPU image baseline.

## 4. Decision needed from the operator

Before opening Phase 7B, the operator should answer:

1. Is there a GPU host with ≥ 8 GB VRAM available for dev / staging?
   - Yes → go with **SadTalker adapter hardening**.
   - No  → go with **local_http_video** or **external_video_api**
     hardening instead.
2. Is there a hard licence constraint that rules out research-use
   weights?
   - Yes → `external_video_api` (vendor-licensed) becomes the only
     path; LivePortrait / Wav2Lip / MuseTalk / SadTalker are all out.
3. Do we need MP4 *output* before we need GPU *capacity*?
   - Yes → `external_video_api` ships fastest; SadTalker ships
     correctest. Pick based on calendar pressure.

The default assumption baked into this recommendation is: **yes to (1),
no to (2), correctness over speed for (3)**. If any of those flip, the
recommendation flips with them.

## 5. What stays unchanged regardless of choice

- `/api/v1/video/generate` keeps its current Phase 6A shape. New states
  add codes; the existing shape is contract-stable.
- The catalog keeps all six provider IDs. Promotion changes `status`
  + adds runbooks; it does not remove deferred entries.
- The light Docker stack keeps zero GPU services.
- No model weights ship inside any image.
- Watermark + C2PA + identity-guard post-passes stay mandatory before a
  job is published.

When Phase 7B lands, this document gets a 7th section:
**"Decision log: Phase 7B chose <provider> on <date> because <reasons>"**.
