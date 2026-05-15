# =============================================================================
# P1.AIVideo backend (FastAPI) — Phase 4C light runtime.
#
# Build context is the repo root (see docker/compose.dev.yml: ``context: ..``).
# Single-stage build: there is no compiled extension to gain from a multi-
# stage layout, and BuildKit's provenance attestation has trouble with
# ``COPY --from=builder /usr/local/lib/...`` of pip's site-packages tree.
#
# This image is metadata-only: NO torch, diffusers, transformers, SadTalker,
# Whisper, SDXL, OpenCV, ffmpeg, moviepy, or other ML/media libraries. No
# model weights are baked in.
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
    && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*
# ``ffmpeg`` pulls in ``ffprobe`` as part of the same Debian package and
# is bounded to audio decode/encode by the Phase 4F conversion service
# (see app/services/audio_conversion.py). NO real video pipeline yet.

# Order matters: ``aivideo-common`` is a path dependency of
# ``aivideo-backend``. Install it first so pip resolves the local source
# rather than trying PyPI.
COPY common/ ./common/
RUN pip install --no-cache-dir -e ./common

COPY backend/pyproject.toml ./backend/pyproject.toml
COPY backend/README.md ./backend/README.md
COPY backend/app/ ./backend/app/
# Editable install: ``aivideo-backend``'s pyproject only enumerates the top
# level ``app`` package, which is fine for editable mode (subpackages
# resolve from the source tree on sys.path) but would lose the subpackages
# under a non-editable install. Same pattern as the dev venv setup.
RUN pip install --no-cache-dir -e ./backend

# Phase 5A+ introduced /api/v1/tts/generate (imports
# ``agents.voice.providers.piper``) and /api/v1/script/generate (imports
# ``agents.scriptwriter.core.registry``). Both need the ``agents`` package
# available in the backend image. The orchestrator image already
# installs it; mirroring it here is the cheapest fix and keeps both
# images on the same import graph.
#
# NOTE: ``agents`` itself does NOT pull torch / diffusers / SadTalker /
# Whisper. The voice + lipsync subpackages are CPU-only stubs until a
# future GPU phase wires the real runtimes (and even then, the GPU
# Dockerfile remains the home for those installs).
COPY agents/ ./agents/
RUN pip install --no-cache-dir -e ./agents

# Storage roots for upload + artifact directories used at runtime. These will
# typically be mounted as named volumes (see compose.dev.yml).
RUN mkdir -p /storage/inputs/audio /storage/inputs/images /storage/inputs/text /storage/artifacts \
    && useradd --create-home --uid 1000 app \
    && chown -R app:app /app /storage

USER app

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "backend"]
