"""Login / logout routes for the local-password backend.

The ``next`` query parameter is honoured on successful login so that
deep-linked admin URLs survive an interstitial login redirect.
"""
from __future__ import annotations

from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.admin.auth.local import authenticate
from app.admin.auth.session import (
    current_user_optional,
    login as session_login,
    logout as session_logout,
)
from app.admin.audit.service import log_action
from app.admin.csrf import CSRFDep
from app.admin.templating import flash, render
from app.db import get_db
from app.models.user import User

router = APIRouter()


def _safe_next(url: str | None, fallback: str = "/admin/") -> str:
    """Allow only same-host relative redirects to prevent open-redirect."""
    if not url:
        return fallback
    parsed = urlparse(url)
    if parsed.netloc or parsed.scheme:
        return fallback
    if not url.startswith("/admin/"):
        return fallback
    return url


@router.get("/login")
def login_form(
    request: Request,
    user: Annotated[User | None, Depends(current_user_optional)],
    next: str = "/admin/",
):
    # Already logged in? Skip the form.
    if user is not None:
        return RedirectResponse(_safe_next(next), status_code=status.HTTP_303_SEE_OTHER)
    return render(request, "login.html", {"next": _safe_next(next), "error": None})


@router.post("/login")
async def login_submit(
    request: Request,
    _: CSRFDep,
    db: Annotated[Session, Depends(get_db)],
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    next: Annotated[str, Form()] = "/admin/",
):
    user = authenticate(db, username=username, password=password)
    if user is None:
        # Audit failed attempts so brute-force shows up in the log.
        log_action(
            db, request,
            actor=None,
            action="auth.login_failed",
            target_type="user",
            target_id=username,
        )
        db.commit()
        return render(
            request, "login.html",
            {
                "next": _safe_next(next),
                "error": "Invalid username or password.",
                "submitted_username": username,
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    session_login(request, user)
    log_action(
        db, request,
        actor=user,
        action="auth.login",
        target_type="user",
        target_id=user.id,
    )
    db.commit()
    flash(request, "success", f"Welcome back, {user.username}.")
    return RedirectResponse(_safe_next(next), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
async def logout(
    request: Request,
    _: CSRFDep,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(current_user_optional)],
):
    if user is not None:
        log_action(
            db, request,
            actor=user,
            action="auth.logout",
            target_type="user",
            target_id=user.id,
        )
        db.commit()
    session_logout(request)
    return RedirectResponse("/admin/login", status_code=status.HTTP_303_SEE_OTHER)
