# =============================================================================
# P1.AIVideo agents — CPU base — Phase 0 stub
#
# Shared base for agents that don't need a GPU at runtime (orchestrator,
# scriptwriter LLM client, editor, qc, publisher, compliance-officer).
#
# GPU-needing agents (voice, face, lipsync) use docker/agents/Dockerfile.cuda.
#
# Real per-agent dependencies and entrypoints land in Phase 1+. Each agent
# may later get its own Dockerfile when its dep set diverges enough.
# =============================================================================
# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.11

FROM python:${PYTHON_VERSION}-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# TODO(phase-3): editor needs ffmpeg; qc needs ffmpeg + tesseract; publisher
# needs c2patool + exiftool. Phase 0 keeps the base lean.
# RUN apt-get update \
#     && apt-get install -y --no-install-recommends ffmpeg \
#     && rm -rf /var/lib/apt/lists/*

# TODO(phase-1+): the `aivideo-common` package is a path dependency of
# this image. Build context must include both `common/` and `agents/`,
# and install order is `common` first, then `agents`:
#
#   COPY common/ ./common/
#   RUN pip install -e ./common
#
#   COPY agents/pyproject.toml ./agents/pyproject.toml
#   COPY agents/ ./agents/
#   RUN pip install -e ./agents

# TODO(phase-1+): per-agent code is injected at build time via an ARG, e.g.:
#   docker build --build-arg AGENT=scriptwriter ...
# ARG AGENT
# COPY agents/${AGENT}/ ./agent/

RUN useradd --create-home --uid 1000 app
USER app

# TODO(phase-1+): replace with the real entrypoint for the chosen AGENT.
CMD ["python", "-c", "import time, sys; print('agent stub — Phase 1+ lands here', flush=True); time.sleep(10**9)"]
