# =============================================================================
# P1.AIVideo — ComfyUI GPU HTTP wrapper — Phase 12W (parity with other model-*).
#
# Pulls a pinned ComfyUI commit + cu128 torch (RTX 5090 Blackwell support).
# Models mount read-only from the host at /comfyui/models so operators
# can share weights with model-sdxl / model-flux / model-sd35 wrappers.
# Custom nodes (operator-supplied) mount at /comfyui/custom_nodes.
#
# Build (~10 GB image):
#   make docker-comfyui-build
# Run:
#   make docker-comfyui-up
# =============================================================================
# syntax=docker/dockerfile:1.7

ARG CUDA_VERSION=12.8.1
ARG UBUNTU_VERSION=22.04
ARG COMFYUI_COMMIT=master

FROM nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu${UBUNTU_VERSION} AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 python3.10-venv python3-pip git ca-certificates curl \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3.10 /usr/local/bin/python && \
    ln -sf /usr/bin/python3.10 /usr/local/bin/python3 && \
    python -m pip install --upgrade pip "setuptools<80"

# Clone ComfyUI at the pinned commit.
ARG COMFYUI_COMMIT
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /comfyui && \
    cd /comfyui && \
    if [ "$COMFYUI_COMMIT" != "master" ]; then git checkout "$COMFYUI_COMMIT"; fi

WORKDIR /comfyui

# Pre-install CLIP without build isolation so pkg_resources lookups work.
RUN python -m pip install --no-build-isolation \
    git+https://github.com/openai/CLIP.git@d50d76daa670286dd6cacf3bcd80b5e4823fc8e1

# Install ComfyUI deps. Force cu128 wheels for Blackwell (sm_120).
RUN python -m pip install \
    --extra-index-url https://download.pytorch.org/whl/cu128 \
    torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 && \
    python -m pip install -r requirements.txt

# Phase IG-B — SDXL-InstantID custom-node deps. insightface builds C
# extensions (needs a toolchain + cython/numpy). onnxruntime (CPU) is used
# because the InstantID workflow runs face analysis with provider="CPU";
# the diffusion itself stays on torch/CUDA. Avoids onnxruntime-gpu's lack of
# a Blackwell (sm_120) wheel.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential python3.10-dev \
    && rm -rf /var/lib/apt/lists/*
RUN python -m pip install "numpy<2" cython && \
    python -m pip install insightface onnxruntime opencv-python-headless

EXPOSE 8188

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8188/system_stats',timeout=2).status==200 else 1)"

CMD ["python", "main.py", "--listen", "0.0.0.0", "--port", "8188"]
