"""CSRF protection for admin forms.

A token is generated per session on first access (lazy), embedded in
every form via ``{{ csrf_token() }}``, and validated on every state-
mutating request (POST/PUT/PATCH/DELETE) before the route handler runs.

Implementation: HMAC-signed token rooted in the session secret, with a
session-scoped salt to avoid one tab's token working in another
session. We do not store the token in the cookie itself — only the
salt — to keep cookies small.
"""
from __future__ import annotations

import hmac
import secrets
from hashlib import sha256
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.admin.auth.session import get_or_generate_session_secret
from app.admin.config import admin_settings

_CSRF_SALT_KEY = "csrf_salt"


def _session_secret() -> bytes:
    return get_or_generate_session_secret().encode("utf-8")


def _ensure_salt(request: Request) -> str:
    salt = request.session.get(_CSRF_SALT_KEY)
    if not salt:
        salt = secrets.token_urlsafe(24)
        request.session[_CSRF_SALT_KEY] = salt
    return salt


def issue_token(request: Request) -> str:
    """Return the CSRF token for this session, creating a salt if needed."""
    salt = _ensure_salt(request)
    return hmac.new(_session_secret(), salt.encode("utf-8"), sha256).hexdigest()


def verify_token(request: Request, submitted: str | None) -> bool:
    """Constant-time compare of submitted token vs the session-derived one."""
    if not submitted:
        return False
    expected = issue_token(request)
    return hmac.compare_digest(submitted, expected)


async def csrf_protect(request: Request) -> None:
    """FastAPI dependency that 403s on missing/invalid CSRF for unsafe verbs.

    Safe methods (GET, HEAD, OPTIONS) skip the check. POST/PUT/PATCH/DELETE
    must include the token either as a form field (``csrf_token``) or as
    an ``X-CSRF-Token`` request header (used by HTMX swaps).
    """
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    token: str | None = request.headers.get("X-CSRF-Token")
    if not token:
        # Lazy-parse the form. We can't consume the body here without
        # invalidating downstream parsing, so we peek via ``await
        # request.form()`` which Starlette caches on the request.
        try:
            form = await request.form()
            token = form.get(admin_settings.csrf_token_name)
        except Exception:
            token = None
    if not verify_token(request, token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="csrf_invalid",
        )


CSRFDep = Annotated[None, Depends(csrf_protect)]
