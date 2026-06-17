"""``@audited`` decorator for FastAPI route handlers.

Wraps a route so that on success an audit row is written, using either
an explicit ``action`` argument or one derived from the route path.

The decorator is intentionally minimal — for routes that need to
capture before/after diffs of a model, call ``log_action()`` directly
inside the handler where you already have the entity in scope.

Example:

    @router.post("/admin/nodes/new")
    @audited(action="node.create", target_type="node")
    async def create_node(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        actor: Annotated[User, Depends(require_role(UserRole.ingester))],
        ...
    ):
        node = Node(...)
        db.add(node)
        db.flush()
        # Decorator picks ``target_id`` from the returned value's ``id`` attr
        # when available, or you can ``request.state.audit_target_id = …``
        return ...
"""
from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.admin.audit.service import log_action
from app.models.user import User


def audited(
    *,
    action: str,
    target_type: str | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator factory.

    The wrapped handler must accept ``request: Request`` and have either
    ``db: Session`` or ``actor: User`` injected via FastAPI deps; the
    decorator inspects ``kwargs`` to find them.
    """

    def _wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        async def _inner(*args: Any, **kwargs: Any) -> Any:
            request: Request | None = kwargs.get("request")
            db: Session | None = kwargs.get("db")
            actor: User | None = kwargs.get("actor")
            result = await fn(*args, **kwargs)
            if request is not None and db is not None:
                target_id = getattr(
                    getattr(request.state, "audit_target_id", None),
                    "value",
                    getattr(request.state, "audit_target_id", None),
                )
                if target_id is None and result is not None:
                    target_id = getattr(result, "id", None)
                log_action(
                    db,
                    request,
                    actor=actor,
                    action=action,
                    target_type=target_type,
                    target_id=target_id,
                    changes=getattr(request.state, "audit_changes", None),
                )
            return result

        return _inner

    return _wrap
