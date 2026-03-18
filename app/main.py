from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import settings
from app.db import wait_for_db
from app.errors import SKAVAError
from app.logging_utils import get_request_id, setup_logging
from app.middleware.request_context import RequestContextMiddleware
from app.routers.access import router as access_router
from app.routers.datalink import router as datalink_router
from app.routers.discovery import router as discovery_router
from app.routers.system import router as system_router
from app.routers.internal_ingestion import router as internal_ingestion_router
from app.routers.soda import router as soda_router
from app.schemas.error import ErrorBody, ErrorResponse

logger = logging.getLogger("skava.app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Fail fast with clear startup error when DB configuration/connectivity is invalid.
    wait_for_db()
    yield


def create_app() -> FastAPI:
    setup_logging(settings.log_level)

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(SKAVAError)
    async def skava_error_handler(_: Request, exc: SKAVAError):
        body = ErrorResponse(
            error=ErrorBody(code=exc.code, message=exc.message, details=exc.details),
            request_id=get_request_id(),
        )
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

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
    app.include_router(discovery_router)
    app.include_router(datalink_router)
    app.include_router(soda_router)
    app.include_router(access_router)
    return app


app = create_app()
