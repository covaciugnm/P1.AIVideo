# =============================================================================
# P1.AIVideo — EchoMimic-V2 GPU HTTP wrapper — Phase 12V.
# antgroup/echomimic_v2 — high-quality talking head + half-body gestures.
# Weights: BadToBest/EchoMimicV2 on HF (~12GB) at /models/lipsync/echomimic.
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

WORKDIR /opt/echomimic-wrapper
RUN python -m pip install --extra-index-url https://download.pytorch.org/whl/cu128 \
    torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1

RUN git clone --depth 1 https://github.com/antgroup/echomimic_v2.git /opt/echomimic-src && \
    cd /opt/echomimic-src && python -m pip install --no-build-isolation \
      "diffusers>=0.30" "transformers>=4.40" "accelerate>=1.0" "einops>=0.7" \
      "omegaconf>=2.3" "opencv-python-headless>=4.5" "librosa>=0.10" \
      "ffmpeg-python>=0.2" "moviepy>=1.0" "scipy>=1.10" "pytorch_lightning>=2.0" \
      "numpy>=1.24,<2"

COPY docker/model-echomimic/requirements.txt /opt/echomimic-wrapper/requirements.txt
RUN python -m pip install --no-cache-dir -r /opt/echomimic-wrapper/requirements.txt
COPY docker/model-echomimic/server.py /opt/echomimic-wrapper/server.py

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/health',timeout=2).status==200 else 1)"
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
