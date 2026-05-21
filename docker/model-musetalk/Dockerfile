# =============================================================================
# P1.AIVideo — MuseTalk GPU HTTP wrapper — Phase 12Y.
#
# TMElyralab/MuseTalk: real-time lip sync (~30 fps on RTX 4090). Higher
# fidelity than Wav2Lip; uses VAE-encoded latent space lip generation.
#
# Weights (~2 GB) — operator-supplied on huggingface TMElyralab/MuseTalk:
#   models/lipsync/musetalk/models/musetalk/pytorch_model.bin
#   models/lipsync/musetalk/models/sd-vae-ft-mse/...
#   models/lipsync/musetalk/models/whisper/...
# =============================================================================
# syntax=docker/dockerfile:1.7
ARG CUDA_VERSION=12.8.1
ARG UBUNTU_VERSION=22.04

# CUDA *devel* base (provides nvcc) — mmcv has NO prebuilt wheel for torch 2.7
# / cu128, so it must be compiled from source; Blackwell (RTX 5090) is sm_120.
FROM nvidia/cuda:${CUDA_VERSION}-devel-ubuntu${UBUNTU_VERSION} AS base

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 HF_HUB_OFFLINE=1 \
    # mmcv source build: target Blackwell sm_120 (+ a couple of common archs).
    TORCH_CUDA_ARCH_LIST="8.9;9.0;12.0" \
    MMCV_WITH_OPS=1 FORCE_CUDA=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 python3.10-venv python3-pip python3.10-dev git ca-certificates curl \
        build-essential ninja-build ffmpeg libgl1 libglib2.0-0 libsndfile1 \
        libgles2-mesa libegl1 \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3.10 /usr/local/bin/python && \
    ln -sf /usr/bin/python3.10 /usr/local/bin/python3 && \
    python -m pip install --upgrade pip "setuptools<70" wheel

WORKDIR /opt/musetalk-wrapper

RUN python -m pip install --extra-index-url https://download.pytorch.org/whl/cu128 \
    torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1

# numpy<2 + cython first; then build mmcv from source (long), then mmdet/mmpose
# via openmim so versions resolve against the just-built mmcv. mmcv builds in
# its OWN layer so the ~8-min sm_120 compile caches once it succeeds.
RUN python -m pip install "numpy<2" cython "setuptools<70" && \
    python -m pip install -v --no-build-isolation "mmcv==2.2.0"
# chumpy (a legacy mmpose dep) breaks under build isolation ("No module named
# 'pip'"), so pre-install it WITHOUT isolation against the env numpy<2/setuptools.
RUN python -m pip install --no-build-isolation chumpy && \
    python -m pip install -U openmim && \
    mim install "mmdet>=3.1,<3.4" "mmpose>=1.1,<1.4"

RUN git clone --depth 1 https://github.com/TMElyralab/MuseTalk.git /opt/musetalk-src && \
    cd /opt/musetalk-src && python -m pip install --no-build-isolation \
      "diffusers==0.30.2" "transformers==4.44.2" "tokenizers<0.20" \
      "accelerate>=0.28" "einops>=0.7" \
      "omegaconf>=2.3" "opencv-python-headless>=4.5" "librosa>=0.10" \
      "ffmpeg-python>=0.2" "moviepy==1.0.3" "huggingface_hub>=0.25" \
      pydub icecream && \
    python -m pip install "numpy<2"

COPY docker/model-musetalk/requirements.txt /opt/musetalk-wrapper/requirements.txt
RUN python -m pip install --no-cache-dir -r /opt/musetalk-wrapper/requirements.txt

COPY docker/model-musetalk/server.py /opt/musetalk-wrapper/server.py

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/health',timeout=2).status==200 else 1)"

CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
