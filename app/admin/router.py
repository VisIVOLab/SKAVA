"""Top-level admin APIRouter and error handlers.

Composes the per-section routers (auth, dashboard, …) and registers
exception handlers that:

* convert 401 ``login_required`` into a 303 redirect to /admin/login
* render 403 / 404 / 500 as branded admin error pages

The router is mounted at ``/admin`` from ``app/main.py``.
"""
from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.admin.routers import auth as auth_routes
from app.admin.routers import dashboard as dashboard_routes
from app.admin.routers import datasets as datasets_routes
from app.admin.routers import nodes as nodes_routes
from app.admin.routers import upload as upload_routes
from app.admin.templating import render

logger = logging.getLogger("skava.admin")

router = APIRouter()
router.include_router(auth_routes.router)
router.include_router(dashboard_routes.router)
router.include_router(nodes_routes.router)
router.include_router(datasets_routes.router)
router.include_router(upload_routes.router)


def _wants_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/html" in accept or accept == ""


def register_admin(app: FastAPI) -> None:
    """Wire the admin router and its error handlers into the FastAPI app.

    Called once from ``app/main.py``. Keeps the wiring concerns in this
    module so ``main.py`` only has to call this single function.
    """
    app.include_router(router, prefix="/admin", tags=["admin"])

    static_dir = Path(__file__).parent / "static"
    if static_dir.is_dir():
        app.mount(
            "/admin/static",
            StaticFiles(directory=str(static_dir)),
            name="admin-static",
        )

    @app.exception_handler(HTTPException)
    async def admin_http_exception_handler(request: Request, exc: HTTPException):
        # Scoped to admin paths only — fall back to the default handler
        # for the rest of the API so JSON error envelopes stay intact.
        if not request.url.path.startswith("/admin"):
            raise exc
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            next_url = quote(request.url.path)
            return RedirectResponse(
                f"/admin/login?next={next_url}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        if not _wants_html(request):
            # HTMX swaps & fetch callers prefer compact error bodies.
            return Response(
                content=str(exc.detail),
                status_code=exc.status_code,
                media_type="text/plain",
            )
        return render(
            request,
            "error.html",
            {"status_code": exc.status_code, "detail": str(exc.detail)},
            status_code=exc.status_code,
        )
