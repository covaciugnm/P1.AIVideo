# =============================================================================
# P1.AIVideo — AUTOMATIC1111 WebUI GPU wrapper — Phase 12W.
#
# Why a custom Dockerfile (not the upstream image):
# - The official Stability-AI/stablediffusion repo was archived/removed
#   from GitHub. A1111's launch_utils.py blindly tries to clone it and
#   exits with "Repository not found". We pre-populate that directory
#   from the CompVis ancestor (same ldm/ module layout) so the clone
#   step is skipped.
# - A1111's requirements pin obsolete Pillow / blendmodes / numpy that
#   have no Python 3.12 wheels. We pin Python 3.10 (the version A1111
#   actually supports) and pre-install the conflict-prone packages
#   without build isolation so pkg_resources lookups don't fail under
#   setuptools 80+.
# - cu128 torch wheels are required for RTX 5090 Blackwell (sm_120).
#
# Build (~12 GB image, ~25 min on first build):
#   make docker-a1111-build
# Run:
#   make docker-a1111-up
# =============================================================================
# syntax=docker/dockerfile:1.7

ARG CUDA_VERSION=12.8.1
ARG UBUNTU_VERSION=22.04

FROM nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu${UBUNTU_VERSION} AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Ubuntu 22.04 ships Python 3.10 in the deadsnakes-free default, which is
# the version A1111 actually supports. We *also* install build deps so
# Pillow / opencv etc. can fall back to source builds if wheels miss.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 python3.10-venv python3.10-dev python3-pip \
        git ca-certificates curl build-essential \
        libgl1 libglib2.0-0 libjpeg-dev zlib1g-dev libpng-dev \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3.10 /usr/local/bin/python && \
    ln -sf /usr/bin/python3.10 /usr/local/bin/python3 && \
    python -m pip install --upgrade pip "setuptools<80"

# Clone A1111 at the master HEAD.
RUN git clone --depth 1 https://github.com/AUTOMATIC1111/stable-diffusion-webui.git /a1111

WORKDIR /a1111

# Create the venv A1111 expects (webui.sh resolves python_cmd in /a1111/venv).
RUN python -m venv venv && \
    venv/bin/pip install --upgrade pip "setuptools<80"

# Pre-install CLIP without build isolation so pkg_resources is visible.
RUN venv/bin/pip install --no-build-isolation \
    git+https://github.com/openai/CLIP.git@d50d76daa670286dd6cacf3bcd80b5e4823fc8e1

# Pre-install torch+torchvision with cu128 wheels (Blackwell support).
# A1111's launch.py will skip its own TORCH_COMMAND when torch is
# already installed at the requested version.
RUN venv/bin/pip install \
    --extra-index-url https://download.pytorch.org/whl/cu128 \
    torch==2.7.1 torchvision==0.22.1

# ===== Pre-populate repositories/ =================================
# A1111 wants 4 sibling repos under repositories/. The first one
# (Stability-AI/stablediffusion) was archived — we substitute with the
# CompVis ancestor which has the same ldm/ layout A1111 imports.
RUN mkdir -p repositories && cd repositories && \
    # Substitute for archived Stability-AI/stablediffusion → CompVis ancestor
    git clone --depth 1 https://github.com/CompVis/stable-diffusion.git stable-diffusion-stability-ai && \
    git clone --depth 1 https://github.com/Stability-AI/generative-models.git generative-models && \
    git clone --depth 1 https://github.com/crowsonkb/k-diffusion.git k-diffusion && \
    git clone --depth 1 https://github.com/salesforce/BLIP.git BLIP && \
    git clone --depth 1 https://github.com/AUTOMATIC1111/stable-diffusion-webui-assets.git stable-diffusion-webui-assets

# CompVis SD1 lacks the SD2 modules A1111 imports (midas/depth model
# stuff). We vendor minimal stubs so the import doesn't crash —
# operator will see depth-model features disabled but everything else
# (txt2img, img2img, SDXL) works.
RUN mkdir -p repositories/stable-diffusion-stability-ai/ldm/modules/midas/midas && \
    printf '"""Stub midas package (SD2-only module not present in CompVis substitute)."""\nimport torch\nclass MiDaSInference(torch.nn.Module):\n    def __init__(self, *args, **kwargs):\n        raise NotImplementedError("MiDaS depth not available with CompVis substitute. Use diffusion-only models.")\n' \
      > repositories/stable-diffusion-stability-ai/ldm/modules/midas/api.py && \
    touch repositories/stable-diffusion-stability-ai/ldm/modules/midas/__init__.py && \
    touch repositories/stable-diffusion-stability-ai/ldm/modules/midas/midas/__init__.py && \
    cp repositories/stable-diffusion-stability-ai/ldm/modules/midas/api.py \
       repositories/stable-diffusion-stability-ai/ldm/modules/midas/midas/midas_net.py && \
    cp repositories/stable-diffusion-stability-ai/ldm/modules/midas/api.py \
       repositories/stable-diffusion-stability-ai/ldm/modules/midas/midas/midas_net_custom.py && \
    cp repositories/stable-diffusion-stability-ai/ldm/modules/midas/api.py \
       repositories/stable-diffusion-stability-ai/ldm/modules/midas/midas/dpt_depth.py && \
    cp repositories/stable-diffusion-stability-ai/ldm/modules/midas/api.py \
       repositories/stable-diffusion-stability-ai/ldm/modules/midas/midas/transforms.py

# Pre-patch requirements pins that block Python 3.10 wheels.
RUN sed -i 's/Pillow==9\.5\.0/Pillow>=10.0/g; s/blendmodes==2022/blendmodes>=2024.1.1/g; s/numpy==1\.26\.2/numpy>=1.26.2,<2.0/g' \
    requirements_versions.txt

# ===== Install A1111's requirements =============================================
RUN venv/bin/pip install -r requirements_versions.txt || \
    (echo "WARN: pinned requirements_versions failed, trying loose requirements.txt" && \
     venv/bin/pip install -r requirements.txt)

# Extra deps A1111 needs at runtime that aren't in requirements.txt but
# ARE imported by the CompVis LDM modules we vendored as the
# stable-diffusion-stability-ai substitute. Without these the launch
# crashes on `ModuleNotFoundError: No module named 'taming'` etc.
RUN venv/bin/pip install --no-build-isolation \
    "taming-transformers-rom1504==0.0.6" \
    "kornia>=0.6" \
    "open-clip-torch>=2.20" || \
    (echo "FALLBACK: try plain taming-transformers from CompVis" && \
     venv/bin/pip install --no-build-isolation \
       "git+https://github.com/CompVis/taming-transformers.git" \
       "kornia>=0.6" "open-clip-torch>=2.20")

# k-diffusion runtime deps (split per package so any individual failure
# is visible in the build log; --no-build-isolation keeps pkg_resources
# available under setuptools<80).
RUN set -ex && for pkg in \
    "dctorch>=0.1" \
    "jsonmerge>=1.9" \
    "resize-right>=0.0.2" \
    "clean-fid>=0.1.35" \
    "scikit-image>=0.21" \
    "lark>=1.1" \
    "omegaconf>=2.3" \
    "inflection>=0.5" \
    "imagesize>=1.4" \
    "safetensors>=0.4" \
    "diffusers>=0.30" \
    "facexlib>=0.3" \
    "tomesd>=0.1" \
    "torchmetrics>=1.0" \
    "torchdiffeq>=0.2" \
    "torchsde>=0.2" \
    "einops>=0.4" \
    "transformers>=4.30" \
    "accelerate>=0.20" \
    "psutil>=5.9" \
    "tqdm>=4.65" \
    "pytorch_lightning>=1.9,<2.0" \
    "GitPython>=3.1" ; do \
      venv/bin/pip install --no-build-isolation "$pkg" || echo "WARN: $pkg failed" ; \
    done

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:7860/sdapi/v1/sd-models',timeout=2).status==200 else 1)"

# --skip-install: deps already installed above; saves boot time.
# --no-download-sd-model: don't auto-pull the v1.5 checkpoint (operator
#   mounts SDXL at /a1111/models/Stable-diffusion).
CMD ["venv/bin/python", "launch.py", \
     "--api", "--listen", "--port", "7860", \
     "--skip-torch-cuda-test", "--skip-install", \
     "--skip-prepare-environment", \
     "--skip-version-check", \
     "--no-download-sd-model", \
     "--no-half-vae"]
