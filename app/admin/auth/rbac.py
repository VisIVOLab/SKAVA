# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""Role-based access control guards.

Used as FastAPI dependencies on route signatures:

    @router.post(
        "/admin/nodes/new",
        dependencies=[Depends(require_role(UserRole.admin, UserRole.ingester))]
    )

The 403 raised here is intercepted by ``router.py`` and rendered as an
HTML error page when the request accepts HTML, or as a JSON error body
for fetch/HTMX requests that asked for JSON.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.admin.auth.session import current_user_required
from app.models.user import User, UserRole


def require_role(*allowed: UserRole) -> Callable[..., User]:
    """Build a dependency that allows only users with one of ``allowed`` roles.

    ``admin`` is implicitly allowed for every route: an admin can do
    anything an ingester or viewer can do.
    """
    allowed_set: set[UserRole] = {UserRole.admin, *allowed}

    def _guard(
        user: Annotated[User, Depends(current_user_required)],
    ) -> User:
        if not user.has_role(*allowed_set):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"requires_role:{','.join(r.value for r in allowed_set)}",
            )
        return user

    return _guard


def require_admin() -> Callable[..., User]:
    """Shortcut for the most-restrictive ``admin``-only routes."""
    return require_role(UserRole.admin)
