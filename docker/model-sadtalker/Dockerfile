# =============================================================================
# P1.AIVideo — SadTalker GPU HTTP wrapper — Phase 10B
#
# A standalone GPU service that the light backend proxies to over HTTP.
# Mirrors the F5TTS-Ro wrapper pattern in docker/model-tts-ro/. Keeps
# torch + SadTalker out of the light backend image.
#
# Build (~8 GB image, ~15 min on first build):
#   make docker-sadtalker-build
#
# Run (requires NVIDIA Container Toolkit on the host):
#   docker compose -f docker/compose.dev.yml --profile sadtalker up -d model-sadtalker
#
# Safety:
# - Weights mount read-only from the host at /models/lipsync/sadtalker.
# - No fake MP4. /sadtalker/generate refuses when weights or runtime
#   are missing, returning a categorised error to the backend.
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
    SADTALKER_HOST=0.0.0.0 \
    SADTALKER_PORT=8080 \
    SADTALKER_MODELS_ROOT=/models/lipsync/sadtalker \
    SADTALKER_SOURCE_DIR=/opt/sadtalker \
    SADTALKER_RESULT_DIR=/storage/artifacts/sadtalker

WORKDIR /app

# OS-level deps: python, ffmpeg (essential — SadTalker pipes audio
# through ffmpeg), git (one-time clone of upstream), libgl/libglib (cv2
# transitive). Slim list — no build tools, we rely on prebuilt wheels.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3.11 \
        python3.11-venv \
        python3-pip \
        ffmpeg \
        git \
        ca-certificates \
        curl \
        libgl1 \
        libglib2.0-0 \
        libsndfile1 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.11 /usr/bin/python \
    && python -m pip install --upgrade pip

# ---------------------------------------------------------------------------
# Torch (cu128 wheels). Pinned to 2.7.1+cu128 — the first stable release
# whose published wheels include sm_120 (Blackwell, RTX 5090) kernel
# binaries. torch 2.6 cu124 wheels stop at sm_90 and crash with "no
# kernel image is available for execution on the device" on Blackwell.
# ---------------------------------------------------------------------------
ARG TORCH_VERSION=2.7.1
ARG TORCHVISION_VERSION=0.22.1
ARG TORCHAUDIO_VERSION=2.7.1
ARG TORCH_INDEX=https://download.pytorch.org/whl/cu128
RUN pip install --index-url "${TORCH_INDEX}" \
        "torch==${TORCH_VERSION}" \
        "torchvision==${TORCHVISION_VERSION}" \
        "torchaudio==${TORCHAUDIO_VERSION}" \
    && python -c "import torch; print('torch:', torch.__version__, 'cuda:', torch.version.cuda)"

# ---------------------------------------------------------------------------
# SadTalker scientific stack — numpy<2, basicsr/facexlib/gfpgan, etc.
# These come from PyPI default index.
# ---------------------------------------------------------------------------
COPY docker/model-sadtalker/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# basicsr import patch — the upstream package imports
# ``torchvision.transforms.functional_tensor`` which was removed in
# torchvision 0.17+. SadTalker depends on basicsr transitively (via
# gfpgan / facexlib). Patch via sed to avoid `import basicsr` (which
# itself loads degradations.py through __init__ → fails before patch).
RUN BASICSR_DIR=$(python -c "import sysconfig; print(sysconfig.get_paths()['purelib'])")/basicsr \
    && DEG="$BASICSR_DIR/data/degradations.py" \
    && test -f "$DEG" || (echo "NOT FOUND: $DEG" && exit 1) \
    && sed -i 's|from torchvision.transforms.functional_tensor import rgb_to_grayscale|from torchvision.transforms.functional import rgb_to_grayscale|' "$DEG" \
    && grep -n "rgb_to_grayscale" "$DEG" \
    && echo "basicsr patched: $DEG"

# ---------------------------------------------------------------------------
# Clone SadTalker upstream. We pin to the v0.0.2 tag the weights match.
# Source is read-only at runtime; we subprocess into inference.py from
# the wrapper. The CLI lives at /opt/sadtalker/inference.py.
# ---------------------------------------------------------------------------
ARG SADTALKER_GIT_URL=https://github.com/OpenTalker/SadTalker.git
ARG SADTALKER_GIT_REF=cd4c0465ae0b54a6f85af57f5c65fec9fe23e7f8
RUN git clone "${SADTALKER_GIT_URL}" /opt/sadtalker \
    && cd /opt/sadtalker \
    && git checkout "${SADTALKER_GIT_REF}" \
    && git log -1 --pretty=oneline \
    && rm -rf /opt/sadtalker/.git

# SadTalker compatibility patches — the upstream repo is frozen since
# 2023 and still uses numpy.float / numpy.int / numpy.complex aliases
# that were removed in numpy 1.20+. We pin numpy 1.26.4 (last 1.x) and
# rewrite the offending references across the source tree. None of
# these changes alter behaviour — they replace removed aliases with
# their plain-Python equivalents.
RUN cd /opt/sadtalker && \
    grep -rln "np\.float\b\|np\.int\b\|np\.complex\b\|np\.bool\b\|np\.object\b\|np\.long\b" \
        --include="*.py" . | tee /tmp/sadtalker-np-deprecated.list && \
    while read -r f; do \
        [ -z "$f" ] && continue; \
        sed -i \
            -e 's/np\.float\b/float/g' \
            -e 's/np\.int\b/int/g' \
            -e 's/np\.complex\b/complex/g' \
            -e 's/np\.bool\b/bool/g' \
            -e 's/np\.object\b/object/g' \
            -e 's/np\.long\b/int/g' \
            "$f"; \
    done < /tmp/sadtalker-np-deprecated.list && \
    echo "patched np.* deprecated aliases in $(wc -l < /tmp/sadtalker-np-deprecated.list) files"

# Additional SadTalker upstream patches that numpy >= 1.24 broke:
# - face3d/util/preprocess.py: np.array([w0,h0,s,t[0],t[1]]) creates an
#   inhomogeneous shape because t[0]/t[1] may be 1-d numpy slices. Cast
#   to float so the resulting array is flat float64.
# - utils/preprocess.py / utils/face_enhancer.py: assorted np.float casts
#   already addressed via the alias sweep above.
RUN sed -i \
        's|np\.array(\[w0, h0, s, t\[0\], t\[1\]\])|np.array([float(w0), float(h0), float(s), float(t[0]), float(t[1])])|' \
        /opt/sadtalker/src/face3d/util/preprocess.py \
    && grep -n "trans_params = np.array" /opt/sadtalker/src/face3d/util/preprocess.py \
    && echo "patched face3d/util/preprocess.py inhomogeneous array"

# SadTalker's inference.py expects ./checkpoints and ./gfpgan/weights
# relative to the source dir. We symlink the operator-mounted weights so
# the upstream CLI finds them.
RUN ln -sfn "${SADTALKER_MODELS_ROOT}/checkpoints" /opt/sadtalker/checkpoints \
    && mkdir -p /opt/sadtalker/gfpgan/weights \
    && ln -sfn "${SADTALKER_MODELS_ROOT}/gfpgan/GFPGANv1.4.pth" /opt/sadtalker/gfpgan/weights/GFPGANv1.4.pth \
    && ls -la /opt/sadtalker/checkpoints /opt/sadtalker/gfpgan/weights || true

# ---------------------------------------------------------------------------
# Wrapper HTTP service.
# ---------------------------------------------------------------------------
COPY docker/model-sadtalker/server.py /app/server.py

# Pre-create the result dir so the non-root user can write to it.
RUN mkdir -p "${SADTALKER_RESULT_DIR}" \
    && useradd --uid 10002 --create-home --shell /bin/false sadtalker \
    && chown -R sadtalker:sadtalker /app /opt/sadtalker "${SADTALKER_RESULT_DIR}"
USER 10002

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
