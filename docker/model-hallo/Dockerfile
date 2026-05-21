# =============================================================================
# P1.AIVideo — Hallo2 GPU HTTP wrapper — Phase 12V.
# fudan-generative-vision/hallo2 — HD/4K talking head, audio-driven.
# Weights ~15GB at /models/lipsync/hallo. ~15GB VRAM at full precision.
# =============================================================================
# syntax=docker/dockerfile:1.7
ARG CUDA_VERSION=12.8.1
ARG UBUNTU_VERSION=22.04
FROM nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu${UBUNTU_VERSION} AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 HF_HUB_OFFLINE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3.10-venv python3-pip python3.10-dev git ca-certificates curl \
    build-essential ffmpeg libgl1 libglib2.0-0 libsndfile1 \
    && rm -rf /var/lib/apt/lists/*
RUN ln -sf /usr/bin/python3.10 /usr/local/bin/python && \
    ln -sf /usr/bin/python3.10 /usr/local/bin/python3 && \
    python -m pip install --upgrade pip "setuptools<80"

WORKDIR /opt/hallo-wrapper
RUN python -m pip install --extra-index-url https://download.pytorch.org/whl/cu128 \
    torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1

RUN git clone --depth 1 https://github.com/fudan-generative-vision/hallo2.git /opt/hallo-src && \
    cd /opt/hallo-src && python -m pip install --no-build-isolation \
      "diffusers>=0.30" "transformers>=4.40" "accelerate>=1.0" "einops>=0.7" \
      "omegaconf>=2.3" "opencv-python-headless>=4.5" "librosa>=0.10" \
      "ffmpeg-python>=0.2" "scipy>=1.10" "decord>=0.6"
# hallo2 inference runtime deps the line above misses (pydub/icecream/
# audio-separator/onnxruntime/av/moviepy/insightface/lpips/mediapipe). We
# deliberately SKIP the repo's xformers/bitsandbytes pins (they'd downgrade
# torch 2.7). numpy pinned <2 LAST so audio-separator can't pull numpy 2.x
# and break torch/cv2.
# numpy<2 + cython FIRST (insightface compiles C extensions against them).
# moviepy pinned 1.0.3 (hallo2 uses the removed moviepy.editor API). xformers
# 0.0.31 with --no-deps so it matches torch 2.7.1 WITHOUT upgrading torch.
RUN python -m pip install --no-cache-dir "numpy<2" cython && \
    python -m pip install --no-cache-dir \
      pydub icecream "audio-separator>=0.17" onnxruntime-gpu av "moviepy==1.0.3" \
      insightface lpips mediapipe && \
    python -m pip install --no-cache-dir --no-deps "xformers==0.0.31" && \
    python -m pip install --no-cache-dir "numpy<2"

# mediapipe (used by hallo2 face analysis) dlopen's OpenGL ES libs at runtime.
# Late layer so it doesn't invalidate the heavy pip layers above.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgles2-mesa libegl1 libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

COPY docker/model-hallo/requirements.txt /opt/hallo-wrapper/requirements.txt
RUN python -m pip install --no-cache-dir -r /opt/hallo-wrapper/requirements.txt
COPY docker/model-hallo/server.py /opt/hallo-wrapper/server.py

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/health',timeout=2).status==200 else 1)"
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
