"""Jinja2 environment setup for the admin templates.

Adds the helpers the templates rely on:

* ``csrf_token()``     — emits the per-session CSRF token
* ``brand``            — current brand colour / name from settings
* ``url_for_static()`` — resolves /admin/static/<path>
* ``flash_messages()`` — pops and renders queued flash messages

Templates are auto-escaped (Jinja2 default for ``.html``).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.admin.config import admin_settings
from app.admin.csrf import issue_token

_TEMPLATES_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
templates.env.globals["brand"] = {
    "color": admin_settings.brand_color,
    "color_dark": admin_settings.brand_color_dark,
    "name": admin_settings.brand_name,
}


def _csrf_token(request: Request) -> str:
    return issue_token(request)


def _flash(request: Request, level: str, message: str) -> None:
    """Queue a flash message in the session for the next render."""
    bucket = request.session.setdefault("_flash", [])
    bucket.append({"level": level, "message": message})


def _consume_flash(request: Request) -> list[dict[str, str]]:
    msgs = request.session.pop("_flash", [])
    return list(msgs)


# Expose request-bound helpers via the template namespace.
templates.env.globals["csrf_token"] = _csrf_token
templates.env.globals["consume_flash"] = _consume_flash


def render(
    request: Request,
    template: str,
    context: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
):
    """Shortcut so handlers don't have to repeat the ``request`` plumbing.

    Uses Starlette 0.36+ TemplateResponse signature (request first). The
    previous ``(name, context)`` form was deprecated and now silently
    misinterprets the context dict as the template name, surfacing as
    ``TypeError: unhashable type: 'dict'`` inside Jinja2's cache lookup.
    """
    return templates.TemplateResponse(
        request, template, context or {}, status_code=status_code
    )


def flash(request: Request, level: str, message: str) -> None:
    """Public flash helper. Levels: ``success | error | info | warning``."""
    _flash(request, level, message)
