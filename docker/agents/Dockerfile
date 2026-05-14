# =============================================================================
# P1.AIVideo agents — CPU base — Phase 4C light runtime.
#
# Phase 4C scope: import every ``agents.*`` package and idle. No real worker
# loop, no Redis stream consumer, no model inference, no GPU.
#
# Build context is the repo root. The image installs three local packages
# in dependency order:
#
#   1. ``aivideo-common``  (path: ./common)
#   2. ``aivideo-backend`` (path: ./backend) — temporary Phase 4C coupling.
#      ``agents/orchestrator/dag.py`` + ``handlers.py`` import
#      ``app.models.*`` and ``app.services.*``. A later phase will move the
#      DB-touching code out of agents (or split it into a shared package)
#      so this dependency disappears. For now we install backend to keep
#      the orchestrator importable.
#   3. ``aivideo-agents`` (path: ./agents)
#
# NO torch / diffusers / transformers / SadTalker / Whisper / SDXL / OpenCV
# / ffmpeg / moviepy. NO ``[voice]`` extra (which would pull piper-tts).
#
# Single-stage build for the same BuildKit attestation reason as the
# backend Dockerfile.
# =============================================================================
# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY common/ ./common/
RUN pip install --no-cache-dir -e ./common

COPY backend/pyproject.toml ./backend/pyproject.toml
COPY backend/README.md ./backend/README.md
COPY backend/app/ ./backend/app/
RUN pip install --no-cache-dir -e ./backend

COPY agents/ ./agents/
RUN pip install --no-cache-dir -e ./agents

# Shared storage roots so any handler that touches the filesystem behaves
# the same way in Docker as in dev. Read-only mounts on the agents side
# would still resolve these paths.
RUN mkdir -p /storage/inputs/audio /storage/inputs/images /storage/inputs/text /storage/artifacts \
    && useradd --create-home --uid 1000 app \
    && chown -R app:app /app /storage

USER app

# Phase 4C light idle launcher — imports everything and sleeps. See
# agents/orchestrator/light_idle.py for the rationale.
CMD ["python", "-m", "agents.orchestrator.light_idle"]
