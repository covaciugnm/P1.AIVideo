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

FROM nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu${UBUNTU_VERSION} AS base

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 HF_HUB_OFFLINE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 python3.10-venv python3-pip git ca-certificates curl \
        ffmpeg libgl1 libglib2.0-0 libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3.10 /usr/local/bin/python && \
    ln -sf /usr/bin/python3.10 /usr/local/bin/python3 && \
    python -m pip install --upgrade pip "setuptools<80"

WORKDIR /opt/musetalk-wrapper

RUN python -m pip install --extra-index-url https://download.pytorch.org/whl/cu128 \
    torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1

RUN git clone --depth 1 https://github.com/TMElyralab/MuseTalk.git /opt/musetalk-src && \
    cd /opt/musetalk-src && python -m pip install --no-build-isolation \
      "diffusers>=0.30" "transformers>=4.40" "accelerate>=1.0" "einops>=0.7" \
      "omegaconf>=2.3" "opencv-python-headless>=4.5" "librosa>=0.10" \
      "ffmpeg-python>=0.2" "moviepy>=1.0" "huggingface_hub>=0.25" \
      "numpy>=1.24,<2"

COPY docker/model-musetalk/requirements.txt /opt/musetalk-wrapper/requirements.txt
RUN python -m pip install --no-cache-dir -r /opt/musetalk-wrapper/requirements.txt

COPY docker/model-musetalk/server.py /opt/musetalk-wrapper/server.py

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/health',timeout=2).status==200 else 1)"

CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
