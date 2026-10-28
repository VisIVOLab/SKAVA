import asyncio
import contextlib
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app.admin.auth.session import get_or_generate_session_secret
from app.admin.config import admin_settings
from app.admin.router import register_admin
from app.config import settings
from app.db import wait_for_db
from app.errors import SKAVAError
from app.logging_utils import get_request_id, setup_logging
from app.middleware.request_context import RequestContextMiddleware
from app.routers.access import router as access_router
from app.routers.datalink import router as datalink_router
from app.routers.discovery import router as discovery_router
from app.routers.federation import router as federation_router
from app.routers.provenance import router as provenance_router
from app.routers.staging import router as staging_router
from app.routers.system import router as system_router
from app.routers.internal_ingestion import router as internal_ingestion_router
from app.routers.soda import router as soda_router
from app.routers.tap import router as tap_router
from app.routers.telemetry import router as telemetry_router
from app.schemas.error import ErrorBody, ErrorResponse

logger = logging.getLogger("skava.app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Fail fast with clear startup error when DB configuration/connectivity is invalid.
    wait_for_db()
    prober = None
    if settings.telemetry_interval_seconds > 0:
        from app.db import SessionLocal
        from app.services.telemetry_service import run_prober

        prober = asyncio.create_task(run_prober(SessionLocal, settings.telemetry_interval_seconds))
    try:
        yield
    finally:
        if prober is not None:
            prober.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await prober


def create_app() -> FastAPI:
    setup_logging(settings.log_level)

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_middleware(RequestContextMiddleware)

    # ── Admin UI session middleware ─────────────────────────────────────
    # Required by Starlette's request.session; must run BEFORE
    # request handlers but is allowed AFTER RequestContextMiddleware so
    # the admin's audit log can read the request_id set there.
    app.add_middleware(
        SessionMiddleware,
        secret_key=get_or_generate_session_secret(),
        session_cookie=admin_settings.session_cookie_name,
        max_age=admin_settings.session_max_age_seconds,
        same_site="lax",
        https_only=admin_settings.session_cookie_secure,
    )

    @app.exception_handler(SKAVAError)
    async def skava_error_handler(_: Request, exc: SKAVAError):
        body = ErrorResponse(
            error=ErrorBody(code=exc.code, message=exc.message, details=exc.details),
            request_id=get_request_id(),
        )
        return JSONResponse(status_code=exc.status_code, content=body.model_dump(),
                            headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError):
        body = ErrorResponse(
            error=ErrorBody(code="invalid_query", message="Invalid request parameters", details=exc.errors()),
            request_id=get_request_id(),
        )
        return JSONResponse(status_code=400, content=body.model_dump())

    @app.exception_handler(HTTPException)
    async def http_error_handler(_: Request, exc: HTTPException):
        body = ErrorResponse(
            error=ErrorBody(code=f"http_{exc.status_code}", message=str(exc.detail)),
            request_id=get_request_id(),
        )
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, exc: Exception):
        logger.exception("unhandled_exception", extra={"error": str(exc)})
        body = ErrorResponse(
            error=ErrorBody(code="internal_error", message="Unexpected server error"),
            request_id=get_request_id(),
        )
        return JSONResponse(status_code=500, content=body.model_dump())

    app.include_router(system_router)
    app.include_router(internal_ingestion_router)
    app.include_router(telemetry_router)
    app.include_router(discovery_router)
    app.include_router(datalink_router)
    app.include_router(soda_router)
    app.include_router(tap_router)
    app.include_router(staging_router)
    app.include_router(provenance_router)
    app.include_router(federation_router)
    app.include_router(access_router)

    # Admin UI: mounts /admin/* and /admin/static, registers its own
    # error handler scoped to admin paths only.
    register_admin(app)
    return app


app = create_app()
