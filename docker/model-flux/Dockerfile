# =============================================================================
# P1.AIVideo — FLUX.1 GPU HTTP wrapper — Phase 12W
#
# A standalone GPU service that the light backend proxies to over HTTP.
# Mirrors the model-sadtalker / model-tts-ro wrapper pattern. Keeps
# torch + diffusers + the 23 GB FLUX weights out of the light backend
# image.
#
# Build (~10-12 GB image, ~20 min on first build):
#   make docker-flux-build
#
# Run (requires NVIDIA Container Toolkit on the host):
#   docker compose -f docker/compose.dev.yml --profile flux up -d model-flux
#
# Safety:
# - Weights mount read-only from the host at /models/image/flux.
# - No fake PNG. /flux/generate refuses when weights or runtime are
#   missing, returning a categorised error to the backend.
# - No auto-download — operator places .safetensors files on disk.
# =============================================================================
# syntax=docker/dockerfile:1.7

ARG CUDA_VERSION=12.8.1
ARG UBUNTU_VERSION=22.04

FROM nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu${UBUNTU_VERSION} AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_HOME=/models/.hf_cache

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3-pip ca-certificates curl \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3.11 /usr/local/bin/python && \
    ln -sf /usr/bin/python3.11 /usr/local/bin/python3 && \
    python -m pip install --upgrade pip

WORKDIR /opt/flux-wrapper

COPY docker/model-flux/requirements.txt /opt/flux-wrapper/requirements.txt
RUN python -m pip install --no-cache-dir -r /opt/flux-wrapper/requirements.txt

COPY docker/model-flux/server.py /opt/flux-wrapper/server.py

EXPOSE 8080

# /storage/artifacts must be mounted (shared volume). Health probe is
# stdlib-only so it returns quickly even before diffusers is imported.
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/health',timeout=2).status==200 else 1)"

CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
