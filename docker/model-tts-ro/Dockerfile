# =============================================================================
# F5TTS-Ro Romanian TTS wrapper — Phase 10A-1
#
# Optional, opt-in service. NOT part of the default backend light image —
# build & run only when an operator wants real Romanian TTS:
#
#   make docker-tts-ro-build
#   make docker-tts-ro-up
#
# Image is CPU-only by default to keep the dev experience portable. For
# real-time Romanian voice cloning, the operator should rebuild this image
# on a CUDA-capable host (override the base + add nvidia runtime).
#
# Safety contract:
# - No automatic model download. The container refuses to call out unless
#   F5TTS_RO_ALLOW_AUTO_DOWNLOAD=true is explicitly set AND the operator's
#   model directory is mounted writable. By default the wrapper returns
#   categorised assets_missing / runtime_missing errors.
# - No fake audio. If torch / f5-tts / model assets are absent, /tts/generate
#   returns a 503-style JSON with a categorised error_code.
# - Reference voice + transcript are operator-supplied under
#   /models/f5tts-ro/reference/.
# =============================================================================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    F5TTS_RO_HOST=0.0.0.0 \
    F5TTS_RO_PORT=8080 \
    F5TTS_RO_MODELS_ROOT=/models/tts/f5tts-ro \
    F5TTS_RO_DEVICE=cpu \
    F5TTS_RO_ALLOW_AUTO_DOWNLOAD=false

# Minimal system deps: ffmpeg for output WAV finalisation, libsndfile for
# torchaudio fallback. NO CUDA drivers — operator can rebuild on CUDA host.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# The wrapper uses only fastapi + uvicorn at the API layer. The heavy
# f5-tts + torch deps are imported lazily inside the request handler so
# the image can boot and serve /health even when those packages aren't
# installed (the wrapper then reports runtime_missing).
COPY docker/model-tts-ro/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /app/requirements.txt

# Phase 11F-CDOROB — opt-in heavy ML layer. Default ON so the wrapper
# image actually generates Romanian audio with cdorob/f5-tts-romanian
# out of the box. Operators who want a torch-free `/health`-only
# wrapper for diagnostics can rebuild with --build-arg INSTALL_F5TTS=false.
#
# torch is the CPU build by default; rebuild on a CUDA host (with a
# CUDA-enabled base image) to get GPU acceleration. F5-TTS itself
# brings transformers, einops, librosa, vocos, etc. as a transitive
# closure (~2 GB image growth).
ARG INSTALL_F5TTS=true
RUN if [ "$INSTALL_F5TTS" = "true" ]; then \
        echo ">> Installing torch + f5-tts (Phase 11F-CDOROB heavy ML layer)"; \
        pip install --index-url https://download.pytorch.org/whl/cpu \
            'torch>=2.4,<3' 'torchaudio>=2.4,<3'; \
        pip install 'f5-tts>=0.7' soundfile; \
    else \
        echo ">> Skipping f5-tts install — /health will report runtime_missing"; \
    fi

COPY docker/model-tts-ro/server.py /app/server.py
COPY docker/model-tts-ro/README.md /app/README.md

EXPOSE 8080

# A non-root user keeps the volume mounts safe.
RUN useradd --uid 10001 --create-home --shell /bin/false ttsro \
    && mkdir -p /storage/artifacts /storage/inputs \
    && chown -R ttsro:ttsro /app /storage
USER ttsro

CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
