# ComfyUI workflow templates — identity-consistent character images

These JSON files are **ComfyUI API-format** workflow templates with named
placeholders that the backend substitutes at submit time (see
`backend/app/services/image_providers/local_wrapper_stub.py::_call_comfyui`).
They are mounted read-only into the backend/orchestrator at the path given by
`COMFYUI_WORKFLOW_DIR` (default `/workflows`), and selected per request by
`workflow_name` (the file stem, e.g. `sdxl_instantid_consistent`).

## Placeholder contract

| Placeholder    | Replaced with                                  | Quoted in template |
|----------------|------------------------------------------------|--------------------|
| `__PROMPT__`   | positive prompt (JSON-escaped)                 | yes (`"__PROMPT__"`) |
| `__NEGATIVE__` | negative prompt (JSON-escaped)                 | yes |
| `__SEED__`     | integer seed                                   | no |
| `__WIDTH__`    | output width                                   | no |
| `__HEIGHT__`   | output height                                  | no |
| `__STEPS__`    | sampler steps                                  | no |
| `__CFG__`      | guidance scale                                 | no |
| `__FACE_REF__` | ComfyUI server filename of the **canonical face** reference (uploaded via `/upload/image` before submit) | yes |
| `__BODY_REF__` | ComfyUI server filename of the **canonical full-body** reference | yes |

Numeric placeholders are written **unquoted** in the JSON (`"width": __WIDTH__`);
string placeholders are written **inside quotes** (`"text": "__PROMPT__"`).

## Templates

| File | Mode | Provider | VRAM | Purpose |
|------|------|----------|------|---------|
| `sdxl_initial.json` | text→image | SDXL | ~10 GB | Propose first candidate faces for a NEW character (no reference yet). |
| `pulid_flux_initial.json` | text→image | FLUX.1-dev | heavy | Higher-quality initial candidates on a big-VRAM box. |
| `sdxl_instantid_consistent.json` | identity-conditioned | SDXL + InstantID | ~10 GB | **Fallback / default on 24 GB.** Same person, new scene/outfit, conditioned on the canonical face. |
| `pulid_flux_consistent.json` | identity-conditioned | FLUX.1-dev + PuLID | heavy (→128 GB box) | **Primary, highest fidelity.** Same person, conditioned on the canonical face. |

Initial generation is plain text-to-image **on purpose**: PuLID/InstantID need a
face reference to condition on, and none exists until the operator promotes a
generated image to `CANONICAL_FACE`. See the two-phase flow in the project docs.

## Required ComfyUI custom nodes

The consistent workflows reference custom-node class names. Install the matching
custom nodes in your ComfyUI (`docker/model-comfyui`) — if your installed nodes
use different `class_type` names, edit the template to match (the placeholder
contract above is what the backend depends on, not the node names).

- **InstantID** (`sdxl_instantid_consistent.json`): cubiq/ComfyUI_InstantID —
  provides `InstantIDModelLoader`, `InstantIDFaceAnalysis`, `ApplyInstantID`,
  plus a standard `ControlNetLoader`.
- **PuLID-FLUX** (`pulid_flux_consistent.json`): balazik/ComfyUI_PuLID_Flux —
  provides `PulidFluxModelLoader`, `PulidFluxInsightFaceLoader`,
  `PulidFluxEvaClipLoader`, `ApplyPulidFlux`, plus FLUX core loaders
  (`UNETLoader`, `DualCLIPLoader`, `VAELoader`).

## Model placement (under the `models/` tree mounted at `/models`)

```
models/
  checkpoints/      sd_xl_base_1.0.safetensors          # SDXL base
  flux/             flux1-dev.safetensors               # FLUX.1-dev unet
  clip/             t5xxl_fp8_e4m3fn.safetensors, clip_l.safetensors
  vae/              ae.safetensors                      # FLUX VAE
  instantid/        ip-adapter.bin
  controlnet/       instantid/diffusion_pytorch_model.safetensors
  pulid/            pulid_flux_v0.9.1.safetensors
  insightface/      models/antelopev2/...               # face analysis (see license note)
```

No weights are auto-downloaded (project rule). Place them manually and point the
ComfyUI `extra_model_paths.yaml` (or symlinks) at `/models`. Verify ComfyUI sees
them: `GET ${COMFYUI_BASE_URL}/object_info` lists loaded node classes; the
ComfyUI UI model dropdowns should show the files.

## VRAM guidance

- **24 GB:** use `sdxl_instantid_consistent` / `sdxl_initial`. PuLID-FLUX will
  OOM if Ollama (qwen3.6-27b) or SadTalker are co-resident.
- **≥48–128 GB:** use `pulid_flux_consistent` for best identity + quality.

## ⚠️ License note

InsightFace pretrained models (antelopev2/buffalo) are released for
**non-commercial** use. Identity drift scoring and the InstantID/PuLID face
analysis depend on them. Review licensing before any commercial deployment;
the drift-scoring service is optional and disabled by default.
