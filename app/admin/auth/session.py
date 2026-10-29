# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""Session lifecycle and ``current_user`` FastAPI dependency.

Sessions are server-signed cookies via Starlette's ``SessionMiddleware``.
We store only the user id and a session epoch in the cookie; the user
record is freshly loaded from the DB on every request so that
deactivation / role-change / password reset take effect immediately
without waiting for the cookie to expire.

The middleware is registered in ``app/main.py``; this module exposes
only the read-side helpers.
"""
from __future__ import annotations

import logging
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.admin.config import admin_settings
from app.db import get_db
from app.models.user import User

logger = logging.getLogger("skava.admin.auth")

SESSION_USER_ID_KEY = "uid"
SESSION_EPOCH_KEY = "epoch"


# Module-level cache: the auto-generated dev secret must be the SAME
# value for every call within the process lifetime, otherwise CSRF
# token issuance (during GET) and verification (during POST) compute
# different HMACs and reject the form with a 403. ``None`` until the
# first call resolves it; thereafter held for the process lifetime.
_cached_session_secret: str | None = None


def get_or_generate_session_secret() -> str:
    """Return the configured session secret, or generate one for dev.

    Logs a loud warning when the secret is generated, since the value
    changes on every container restart (invalidating sessions).
    Production deployments MUST set ``ADMIN_SESSION_SECRET``.

    The result is cached at module level so every caller in this
    process — SessionMiddleware setup, CSRF token issuance, CSRF
    verification — agrees on the same value. Without the cache, each
    call to this function in dev mode generated a fresh ``secrets.
    token_urlsafe(64)`` and every form submission failed CSRF.
    """
    global _cached_session_secret
    if _cached_session_secret is not None:
        return _cached_session_secret
    if admin_settings.session_secret:
        _cached_session_secret = admin_settings.session_secret
        return _cached_session_secret
    _cached_session_secret = secrets.token_urlsafe(64)
    logger.warning(
        "ADMIN_SESSION_SECRET not set — generated a transient one. "
        "Sessions will be invalidated on every restart. "
        "Set ADMIN_SESSION_SECRET to a stable random value before deploying."
    )
    return _cached_session_secret


def login(request: Request, user: User) -> None:
    """Mark the request's session as authenticated for ``user``.

    The session epoch lets us invalidate all of a user's sessions in
    one shot — bump the user's epoch in the DB (future feature) and
    every existing cookie becomes unrecognised on the next request.
    """
    request.session[SESSION_USER_ID_KEY] = user.id
    request.session[SESSION_EPOCH_KEY] = 1


def logout(request: Request) -> None:
    """Clear the session cookie."""
    request.session.clear()


def _load_current_user(
    request: Request, db: Session
) -> User | None:
    uid = request.session.get(SESSION_USER_ID_KEY)
    if not uid:
        return None
    user = db.get(User, uid)
    if user is None or not user.is_active:
        # Stale cookie — clear so the next page renders as anonymous.
        request.session.clear()
        return None
    return user


def current_user_optional(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User | None:
    """Return the current user or ``None`` if not authenticated.

    Use this on pages that can render anonymously (e.g. ``/login``).
    """
    return _load_current_user(request, db)


def current_user_required(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Return the current user, redirecting to login if not authenticated.

    The HTTPException is intercepted by the admin error handler in
    ``router.py`` and converted into a 303 redirect to ``/admin/login``
    with the original URL preserved as ``?next=``.
    """
    user = _load_current_user(request, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="login_required",
        )
    return user
