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
    characters,
    export,
    healthz,
    jobs,
    providers,
    qc,
    script,
    secrets,
    system,
    tts,
    uploads,
    video,
)
from app.core.config import settings
from app.core.db import get_sessionmaker, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Phase 13 — capture every stdlib log record into an in-memory ring
    # buffer so the right-sidebar "Backend" tab can render live logs.
    from app.core import log_buffer

    log_buffer.install()
    import logging

    logging.getLogger(__name__).info("backend.startup: log buffer attached")
    await init_db()
    logging.getLogger(__name__).info("backend.startup: database initialized")
    # Phase 12X — push every persisted secret into os.environ so adapter
    # code that reads ``os.environ.get(...)`` survives Docker restarts.
    try:
        sm = get_sessionmaker()
        async with sm() as session:
            from app.services import secrets_service

            count = await secrets_service.load_into_env(session)
            if count:
                import logging

                logging.getLogger(__name__).info(
                    "Loaded %d API secrets from DB into os.environ", count
                )
    except Exception as exc:  # pragma: no cover — defensive
        import logging

        logging.getLogger(__name__).warning(
            "Could not load API secrets at startup: %s", exc
        )
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

    # Phase 13B — blanket request logger. Emits INFO on:
    #   - every mutating verb (POST/PATCH/DELETE) — start + end
    #   - every non-2xx response (so the operator sees rejections live)
    # Skips GET /healthz + GET /api/v1/system/logs/backend to avoid
    # log-amplification feedback loops from the sidebar polling itself.
    import logging
    import time
    from starlette.types import Receive, Scope, Send

    _request_logger = logging.getLogger("app.request")
    _SKIP_PATHS = {"/healthz", "/api/v1/system/logs/backend"}

    @app.middleware("http")
    async def _log_request(request, call_next):  # type: ignore[no-untyped-def]
        path = request.url.path
        method = request.method
        skip = path in _SKIP_PATHS
        mutating = method in {"POST", "PATCH", "PUT", "DELETE"}
        if not skip and mutating:
            _request_logger.info("request.start %s %s", method, path)
        t0 = time.perf_counter()
        response = await call_next(request)
        ms = int((time.perf_counter() - t0) * 1000)
        status_code = response.status_code
        if not skip and (mutating or status_code >= 400):
            level = logging.WARNING if status_code >= 400 else logging.INFO
            _request_logger.log(
                level, "request.end %s %s %d %dms", method, path, status_code, ms
            )
        return response
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
    # Phase 8B: /api/v1/export/finalize — real ffmpeg final export.
    app.include_router(export.router)
    # Phase 8C: /api/v1/qc/inspect — on-demand real media QC.
    app.include_router(qc.router)
    # Phase 12: /api/v1/characters/* CRUD + image library + script context.
    app.include_router(characters.router)
    # Phase 12X: /api/v1/secrets/* DB-backed API key store + test probes.
    app.include_router(secrets.router)
    return app


app = create_app()
