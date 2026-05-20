set -e
cd "$(dirname "$0")/.."
echo "[1/4] InstantID ip-adapter.bin (~1.7GB)"
curl -fSL --retry 3 -o models/image/instantid/ip-adapter.bin \
  https://huggingface.co/InstantX/InstantID/resolve/main/ip-adapter.bin
echo "[2/4] InstantID ControlNet safetensors (~2.5GB)"
curl -fSL --retry 3 -o models/image/controlnet/instantid/diffusion_pytorch_model.safetensors \
  https://huggingface.co/InstantX/InstantID/resolve/main/ControlNetModel/diffusion_pytorch_model.safetensors
echo "[3/4] InstantID ControlNet config.json"
curl -fSL --retry 3 -o models/image/controlnet/instantid/config.json \
  https://huggingface.co/InstantX/InstantID/resolve/main/ControlNetModel/config.json
echo "[4/4] antelopev2 insightface (~360MB)"
curl -fSL --retry 3 -o /tmp/antelopev2.zip \
  https://huggingface.co/MonsterMMORPG/tools/resolve/main/antelopev2.zip
mkdir -p models/image/insightface/models
cd models/image/insightface/models && rm -rf antelopev2 && unzip -o /tmp/antelopev2.zip >/dev/null && echo "antelopev2 unzipped"
echo "DOWNLOADS_DONE"
