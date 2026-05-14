"""FastAPI application factory — Phase 1: metadata-only flow.

No model inference, no video generation, no lip-sync. The app validates
briefs, persists job metadata, and emits a job-created event so the
orchestrator can run the intake policy gate.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    artifacts,
    audio_fit,
    healthz,
    jobs,
    providers,
    script,
    system,
    tts,
    uploads,
    video,
)
from app.core.config import settings
from app.core.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="P1.AIVideo backend",
        version="0.1.0",
        description="Phase 1: metadata-only flow. No inference, no media generation.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(healthz.router)
    app.include_router(jobs.router)
    # Phase 4B: mirror the /jobs router under /api/v1 so the frontend can
    # speak a single /api/v1/* prefix for every endpoint. The original
    # /jobs/* routes stay for backward compatibility with the existing
    # phase tests.
    app.include_router(jobs.router, prefix="/api/v1")
    # Phase 4A-2: /api/v1/uploads/{text,audio,image} + /api/v1/jobs/from-inputs
    app.include_router(uploads.uploads_router)
    app.include_router(uploads.jobs_v1_router)
    # Phase 4B: /api/v1/stages, /api/v1/artifact-types,
    # /api/v1/config/ui-options, /api/v1/system/status.
    app.include_router(system.router)
    # Phase 4F: providers metadata, TTS preview, artifact content serving.
    app.include_router(providers.router)
    app.include_router(tts.router)
    app.include_router(artifacts.router)
    # Phase 5B: /api/v1/script/generate preview hook.
    app.include_router(script.router)
    # Phase 5C: /api/v1/audio/fit-check.
    app.include_router(audio_fit.router)
    # Phase 6A: /api/v1/video/generate contract endpoint (metadata-only).
    app.include_router(video.router)
    return app


app = create_app()
