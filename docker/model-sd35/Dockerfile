# =============================================================================
# P1.AIVideo — Stable Diffusion 3.5 Large GPU HTTP wrapper — Phase 12W
#
# Same pattern as model-flux. SD3.5-large is GATED on Hugging Face; the
# operator must accept the Stability AI license + put HF_TOKEN in their
# env when downloading. Once weights are on disk, the wrapper runs
# fully offline.
#
# Build (~10 GB image):
#   make docker-sd35-build
# Run:
#   docker compose -f docker/compose.dev.yml --profile sd35 up -d model-sd35
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

WORKDIR /opt/sd35-wrapper

COPY docker/model-sd35/requirements.txt /opt/sd35-wrapper/requirements.txt
RUN python -m pip install --no-cache-dir -r /opt/sd35-wrapper/requirements.txt

COPY docker/model-sd35/server.py /opt/sd35-wrapper/server.py

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/health',timeout=2).status==200 else 1)"

CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
