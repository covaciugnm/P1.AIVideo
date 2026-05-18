# =============================================================================
# P1.AIVideo — Stable Diffusion XL GPU HTTP wrapper — Phase 12W
#
# Lighter sibling of model-flux (SDXL ≈ 7 GB instead of 24 GB).
# Mirrors the same pattern: CUDA base + diffusers + FastAPI server.
#
# Build (~9 GB image):
#   make docker-sdxl-build
#
# Run:
#   docker compose -f docker/compose.dev.yml --profile sdxl up -d model-sdxl
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

WORKDIR /opt/sdxl-wrapper

COPY docker/model-sdxl/requirements.txt /opt/sdxl-wrapper/requirements.txt
RUN python -m pip install --no-cache-dir -r /opt/sdxl-wrapper/requirements.txt

COPY docker/model-sdxl/server.py /opt/sdxl-wrapper/server.py

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/health',timeout=2).status==200 else 1)"

CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
