# =============================================================================
# P1.AIVideo frontend (Next.js 14 App Router) — Phase 4C light runtime.
#
# Build context is the repo root (see docker/compose.dev.yml). Three stages:
#
#   deps     → npm ci against frontend/package*.json
#   builder  → COPY frontend/, npm run lint, npm run build
#   runner   → minimal node image, copies .next + node_modules, runs
#              ``npm run start`` as the non-root ``node`` user.
#
# NO Tailwind, no UI / charting / media libraries are pulled in beyond
# what frontend/package.json already declares.
# =============================================================================
# syntax=docker/dockerfile:1.7

ARG NODE_VERSION=20

# ---------------------------------------------------------------------------
# Stage 1 — deps
# ---------------------------------------------------------------------------
FROM node:${NODE_VERSION}-alpine AS deps
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund


# ---------------------------------------------------------------------------
# Stage 2 — builder
# ---------------------------------------------------------------------------
FROM node:${NODE_VERSION}-alpine AS builder
WORKDIR /app

# The base URL is baked into the JS bundle at build time because Next.js
# inlines NEXT_PUBLIC_* values. Default points at the host port the dev
# compose publishes; override at build time with --build-arg.
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production

COPY --from=deps /app/node_modules ./node_modules
COPY frontend/ ./

RUN npm run lint && npm run build


# ---------------------------------------------------------------------------
# Stage 3 — runner
# ---------------------------------------------------------------------------
FROM node:${NODE_VERSION}-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# next start needs package.json, the built .next directory, public/, and
# the production node_modules.
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/package-lock.json ./package-lock.json
COPY --from=builder /app/next.config.mjs ./next.config.mjs
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules

USER node

EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=5 \
    CMD wget --spider -q http://localhost:3000/ || exit 1

CMD ["npm", "run", "start"]
