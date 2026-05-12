# =============================================================================
# P1.AIVideo backend (FastAPI) — Phase 0 stub
#
# Real dependencies and application code land in Phase 1. The stub command
# keeps the container alive so docker compose works during scaffolding.
# =============================================================================
# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.11

FROM python:${PYTHON_VERSION}-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# TODO(phase-1): install minimal OS deps if needed (e.g. curl for healthchecks).
# RUN apt-get update \
#     && apt-get install -y --no-install-recommends curl \
#     && rm -rf /var/lib/apt/lists/*

# TODO(phase-1): copy backend/pyproject.toml and install.
# COPY backend/pyproject.toml ./pyproject.toml
# RUN pip install -e .

# TODO(phase-1): copy application source.
# COPY backend/ ./

# Create a non-root user. The numeric uid is stable across rebuilds so bind
# mounts and named volumes have predictable ownership.
RUN useradd --create-home --uid 1000 app
USER app

EXPOSE 8000

# TODO(phase-1): real healthcheck once /healthz exists.
# HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
#   CMD curl -fsS http://localhost:8000/healthz || exit 1

# TODO(phase-1): replace with `["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`
CMD ["python", "-c", "import time, sys; print('backend stub — Phase 1 lands here', flush=True); time.sleep(10**9)"]
