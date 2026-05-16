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

# Phase TTS-rescue — optional piper-tts install so the DAG worker can
# actually synthesize on the voice stage. Default OFF to preserve the
# light agents image; build with ``--build-arg INSTALL_PIPER=true`` to
# enable real Piper synthesis (CPU-only, ~80 MB onnxruntime). When
# disabled the voice stage continues to surface
# ``tts_runtime_missing`` as documented in docs/runbooks/piper-runtime.md.
ARG INSTALL_PIPER=false
RUN if [ "$INSTALL_PIPER" = "true" ]; then \
        echo ">> Installing piper-tts in orchestrator image"; \
        pip install --no-cache-dir 'piper-tts>=1.2'; \
    else \
        echo ">> Skipping piper-tts install in orchestrator (build with --build-arg INSTALL_PIPER=true to enable)"; \
    fi

# Phase 10A-1 — the DAG runner reads its stage order from
# ``pipelines/reel_default.yaml`` (and Phase-3 variants live alongside).
# The light_idle launcher never needed this, but the real worker does.
COPY pipelines/ ./pipelines/

# Shared storage roots so any handler that touches the filesystem behaves
# the same way in Docker as in dev. Read-only mounts on the agents side
# would still resolve these paths.
RUN mkdir -p /storage/inputs/audio /storage/inputs/images /storage/inputs/text /storage/artifacts \
    && useradd --create-home --uid 1000 app \
    && chown -R app:app /app /storage

USER app

# Phase 10A-1 real DAG worker. Reads pending_compliance jobs from the DB
# and drives them through the metadata-only / categorised-soft-fail DAG.
# Respects ORCHESTRATOR_MODE — set ``idle`` to fall back to the Phase 4C
# import-only smoke. See agents/orchestrator/run_worker.py.
CMD ["python", "-m", "agents.orchestrator.run_worker"]
