# SDXL-InstantID model manifest (24 GB machine)

Required for the identity-consistent ComfyUI workflow
`workflows/comfyui/sdxl_instantid_consistent.json`. Weights are **git-ignored**
(large) — install manually. No silent auto-download by the app.

## Custom node
- `cubiq/ComfyUI_InstantID` → `docker/model-comfyui/custom_nodes/ComfyUI_InstantID`
  (mounted at `/comfyui/custom_nodes`). Node classes: `InstantIDModelLoader`,
  `InstantIDFaceAnalysis`, `ApplyInstantID`. Python deps (baked into the image
  Dockerfile): `insightface`, `onnxruntime` (CPU), `opencv-python-headless`.

## Required files, paths and sizes (verified present 2026-05-20)

| File | Host path (→ ComfyUI path) | Size | Source |
|---|---|---|---|
| InstantID ip-adapter | `models/image/instantid/ip-adapter.bin` → `/comfyui/models/instantid/ip-adapter.bin` | 1.69 GB | `https://huggingface.co/InstantX/InstantID/resolve/main/ip-adapter.bin` |
| InstantID ControlNet | `models/image/controlnet/instantid/diffusion_pytorch_model.safetensors` → `/comfyui/models/controlnet/instantid/...` | 2.50 GB | `https://huggingface.co/InstantX/InstantID/resolve/main/ControlNetModel/diffusion_pytorch_model.safetensors` |
| ControlNet config | `models/image/controlnet/instantid/config.json` | 1.4 KB | `.../ControlNetModel/config.json` |
| antelopev2 (insightface) | `models/image/insightface/models/antelopev2/{1k3d68,2d106det,genderage,glintr100,scrfd_10g_bnkps}.onnx` → `/comfyui/models/insightface/models/antelopev2/` | 408 MB | `https://huggingface.co/MonsterMMORPG/tools/resolve/main/antelopev2.zip` |
| SDXL base (already present) | `models/image/sdxl/sdxl-base-1.0/sd_xl_base_1.0.safetensors` → `/comfyui/models/checkpoints/sdxl-base-1.0/...` | 6.9 GB | (pre-existing) |

## Download commands
See `scripts/download_instantid_models.sh` (idempotent; uses curl).

## License note
InsightFace antelopev2 is released for **non-commercial** use. Review before
any commercial deployment. The diffusion path (SDXL) is separate.
