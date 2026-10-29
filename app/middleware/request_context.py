# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
import logging
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.logging_utils import reset_request_id, set_request_id
from app.metrics import record_http_request

logger = logging.getLogger("skava.request")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        token = set_request_id(request_id)

        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            elapsed = time.perf_counter() - start
            record_http_request(request.method, request.url.path, status_code, elapsed)
            logger.info(
                "request_completed",
                extra={
                    "endpoint": request.url.path,
                    "query_params": dict(request.query_params),
                    "status_code": status_code,
                    "execution_time_ms": round(elapsed * 1000, 3),
                },
            )
            reset_request_id(token)
