# =============================================================================
# P1.AIVideo — Mochi-1 GPU HTTP wrapper — Phase 12V.
# genmoai/models Mochi-1 — txt→vid SOTA. ~60GB VRAM → ~16GB 4-bit BNB.
# Weights ~30GB at /models/video/mochi.
# =============================================================================
# syntax=docker/dockerfile:1.7
ARG CUDA_VERSION=12.8.1
ARG UBUNTU_VERSION=22.04
FROM nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu${UBUNTU_VERSION} AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 HF_HUB_OFFLINE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3.11-venv python3-pip git ca-certificates curl \
    ffmpeg libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
RUN ln -sf /usr/bin/python3.11 /usr/local/bin/python && \
    ln -sf /usr/bin/python3.11 /usr/local/bin/python3 && \
    python -m pip install --upgrade pip "setuptools<80"

WORKDIR /opt/mochi-wrapper
RUN python -m pip install --extra-index-url https://download.pytorch.org/whl/cu128 \
    torch==2.7.1 torchvision==0.22.1
COPY docker/model-mochi/requirements.txt /opt/mochi-wrapper/requirements.txt
RUN python -m pip install --no-cache-dir -r /opt/mochi-wrapper/requirements.txt
COPY docker/model-mochi/server.py /opt/mochi-wrapper/server.py

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/health',timeout=2).status==200 else 1)"
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
