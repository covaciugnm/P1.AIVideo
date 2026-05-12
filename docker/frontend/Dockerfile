# =============================================================================
# P1.AIVideo frontend (Next.js) — Phase 0 stub
#
# Real Next.js app and build steps land in Phase 4. The stub keeps the
# container alive so docker compose works during scaffolding.
# =============================================================================
# syntax=docker/dockerfile:1.7

ARG NODE_VERSION=20

FROM node:${NODE_VERSION}-alpine AS base

WORKDIR /app

# TODO(phase-4): copy package manifests and install.
# COPY frontend/package.json frontend/package-lock.json* ./
# RUN npm ci --omit=dev

# TODO(phase-4): copy source and build.
# COPY frontend/ ./
# RUN npm run build

# Run as the built-in `node` user.
USER node

EXPOSE 3000

# TODO(phase-4): replace with `["npm", "run", "start"]`
CMD ["node", "-e", "console.log('frontend stub — Phase 4 lands here'); setInterval(()=>{}, 1e9)"]
