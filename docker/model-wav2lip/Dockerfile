# =============================================================================
# P1.AIVideo — Wav2Lip GPU HTTP wrapper — Phase 12Y.
#
# Lip-sync video generator. Takes (face image OR source video) + audio,
# produces a video with the mouth re-animated to match the speech.
# Lighter than SadTalker (~300 MB model) and often sharper for talking-
# head footage.
#
# Model weights (~400 MB) operator-supplied:
#   models/lipsync/wav2lip/wav2lip_gan.pth
#   models/lipsync/wav2lip/wav2lip.pth (optional alt)
#
# Build:
#   make docker-wav2lip-build
# Run:
#   make docker-wav2lip-up
# =============================================================================
# syntax=docker/dockerfile:1.7

ARG CUDA_VERSION=12.8.1
ARG UBUNTU_VERSION=22.04

FROM nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu${UBUNTU_VERSION} AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 python3.10-venv python3-pip git ca-certificates curl \
        ffmpeg libgl1 libglib2.0-0 libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3.10 /usr/local/bin/python && \
    ln -sf /usr/bin/python3.10 /usr/local/bin/python3 && \
    python -m pip install --upgrade pip "setuptools<80"

WORKDIR /opt/wav2lip-wrapper

# Pre-install torch with cu128 (Blackwell support).
RUN python -m pip install \
    --extra-index-url https://download.pytorch.org/whl/cu128 \
    torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1

# Clone Wav2Lip reference (Rudrabha is the original author).
RUN git clone --depth 1 https://github.com/Rudrabha/Wav2Lip.git /opt/wav2lip-src && \
    cd /opt/wav2lip-src && python -m pip install --no-build-isolation \
      "librosa>=0.10" "opencv-python-headless>=4.5" "numpy>=1.24,<2" \
      "tqdm>=4.65" "scipy>=1.10" "numba>=0.58"

# Phase 15D — librosa 0.10+ enforces keyword-only ``sr``/``n_fft`` on
# ``librosa.filters.mel``; the original Wav2Lip 2020 code passes them
# positionally. Patch in-place so the runtime works with modern librosa.
RUN sed -i 's/librosa.filters.mel(hp.sample_rate, hp.n_fft,/librosa.filters.mel(sr=hp.sample_rate, n_fft=hp.n_fft,/' \
    /opt/wav2lip-src/audio.py && \
    grep "librosa.filters.mel" /opt/wav2lip-src/audio.py

COPY docker/model-wav2lip/requirements.txt /opt/wav2lip-wrapper/requirements.txt
RUN python -m pip install --no-cache-dir -r /opt/wav2lip-wrapper/requirements.txt

COPY docker/model-wav2lip/server.py /opt/wav2lip-wrapper/server.py

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/health',timeout=2).status==200 else 1)"

CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
