"""FastAPI application factory — Phase 1: metadata-only flow.

No model inference, no video generation, no lip-sync. The app validates
briefs, persists job metadata, and emits a job-created event so the
orchestrator can run the intake policy gate.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import healthz, jobs
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
    return app


app = create_app()
