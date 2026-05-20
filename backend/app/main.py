"""FastAPI application factory — Phase 1: metadata-only flow.

No model inference, no video generation, no lip-sync. The app validates
briefs, persists job metadata, and emits a job-created event so the
orchestrator can run the intake policy gate.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    artifacts,
    audio_fit,
    auth,
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
    users,
    video,
)
from app.core.config import settings
from app.core.db import get_sessionmaker, init_db
from app.core.security import require_active_user, require_super_admin


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
    # Security remediation — validate auth config + bootstrap protected
    # super admin. Fails fast (safe message) if required secrets are missing.
    if settings.p1_auth_enabled:
        settings.assert_auth_config()
        try:
            sm0 = get_sessionmaker()
            async with sm0() as session0:
                from app.services import auth_service

                await auth_service.bootstrap_super_admin(session0)
        except Exception:
            logging.getLogger(__name__).exception("backend.startup: super-admin bootstrap failed")
            raise
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
    # --- Public routes (no auth): health + auth (login/register) ---
    app.include_router(healthz.router)
    app.include_router(auth.router)
    # --- Authenticated product routes (guard no-ops when auth disabled) ---
    authed = [Depends(require_active_user)]
    app.include_router(jobs.router, dependencies=authed)
    # Phase 4B: mirror the /jobs router under /api/v1 so the frontend can
    # speak a single /api/v1/* prefix for every endpoint.
    app.include_router(jobs.router, prefix="/api/v1", dependencies=authed)
    app.include_router(uploads.uploads_router, dependencies=authed)
    app.include_router(uploads.jobs_v1_router, dependencies=authed)
    # system: status/config endpoints stay reachable (low-risk metadata used
    # by the shell); the sensitive /system/logs/backend is super-admin-gated
    # at the route level inside system.py.
    app.include_router(system.router)
    app.include_router(providers.router, dependencies=authed)
    app.include_router(tts.router, dependencies=authed)
    app.include_router(artifacts.router, dependencies=authed)
    app.include_router(script.router, dependencies=authed)
    app.include_router(audio_fit.router, dependencies=authed)
    app.include_router(video.router, dependencies=authed)
    app.include_router(export.router, dependencies=authed)
    app.include_router(qc.router, dependencies=authed)
    app.include_router(characters.router, dependencies=authed)
    # --- Super-admin-only routes: secrets + user management ---
    app.include_router(secrets.router, dependencies=[Depends(require_super_admin)])
    app.include_router(users.router)  # router-level require_super_admin inside
    return app


app = create_app()
