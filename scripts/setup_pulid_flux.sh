#!/usr/bin/env bash
# Reproducible setup for the PuLID-FLUX identity image engine.
#
# Custom nodes + multi-GB weights are NOT committed (see
# docker/model-comfyui/custom_nodes/.gitignore). This script clones the node,
# applies the ComfyUI-compat patch, and downloads the weights into ./models.
# Idempotent. Run from the repo root.
set -euo pipefail
cd "$(dirname "$0")/.."

NODE_DIR="docker/model-comfyui/custom_nodes/ComfyUI_PuLID_Flux_ll"
HOOK="$NODE_DIR/PulidFluxHook.py"

echo "[1/3] PuLID-Flux custom node"
if [ ! -d "$NODE_DIR" ]; then
  git clone --depth 1 https://github.com/lldacing/ComfyUI_PuLID_Flux_ll.git "$NODE_DIR"
fi
# Patch: newer ComfyUI passes timestep_zero_index to the patched flux forward.
# Absorb unknown kwargs so PuLID stays compatible.
if ! grep -q "absorb newer ComfyUI flux args" "$HOOK"; then
  python3 - "$HOOK" <<'PY'
import sys
p=sys.argv[1]; s=open(p).read()
old="    attn_mask: Tensor = None,\n) -> Tensor:"
new="    attn_mask: Tensor = None,\n    **kwargs,  # absorb newer ComfyUI flux args (e.g. timestep_zero_index)\n) -> Tensor:"
assert old in s, "patch anchor not found (node version changed?)"
open(p,"w").write(s.replace(old,new,1))
print("  patched PulidFluxHook.py")
PY
fi

echo "[2/3] weights (~18GB, non-gated mirrors)"
mkdir -p models/unet models/clip models/vae models/pulid
dl() { [ -f "$1" ] && { echo "  have $(basename "$1")"; return; }; echo "  get $(basename "$1")"; curl -fSL --retry 3 -o "$1" "$2"; }
dl models/unet/flux1-dev-fp8.safetensors        https://huggingface.co/Kijai/flux-fp8/resolve/main/flux1-dev-fp8.safetensors
dl models/clip/t5xxl_fp8_e4m3fn.safetensors     https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors
dl models/clip/clip_l.safetensors               https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors
dl models/pulid/pulid_flux_v0.9.1.safetensors   https://huggingface.co/guozinan/PuLID/resolve/main/pulid_flux_v0.9.1.safetensors
# FLUX VAE (shared with FLUX.1-schnell already on disk if present)
if [ -f models/image/flux/flux.1-schnell/ae.safetensors ]; then
  cp -n models/image/flux/flux.1-schnell/ae.safetensors models/vae/ae.safetensors
else
  dl models/vae/ae.safetensors https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/ae.safetensors
fi

echo "[3/3] enable the engine"
echo "  set in .env:  IMAGE_PROVIDER_DEFAULT=pulid_flux"
echo "  rebuild:      docker compose --env-file .env -f docker/compose.dev.yml build model-comfyui"
echo "  restart:      docker compose --env-file .env -f docker/compose.dev.yml up -d model-comfyui"
echo "DONE. EVA-CLIP (~1.7GB) auto-downloads into models/clip/.cache on first run."
