"""Direct write-side helper for the audit log.

Most handlers use the ``@audited`` decorator instead; this module is
the lower-level primitive it builds on, and is also called directly
from places where a decorator does not fit (e.g. login success).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.logging_utils import get_request_id
from app.models.audit_log import AuditLog
from app.models.user import User

logger = logging.getLogger("skava.admin.audit")


def log_action(
    db: Session,
    request: Request,
    *,
    actor: User | None,
    action: str,
    target_type: str | None = None,
    target_id: str | int | None = None,
    changes: dict[str, Any] | None = None,
) -> AuditLog:
    """Insert one audit row. Does NOT commit — caller owns the transaction.

    ``actor=None`` is allowed and used for anonymous-context events
    such as failed logins. The label falls back to ``"<anonymous>"`` or
    the supplied IP so the row is still legible.
    """
    label = (
        f"{actor.username} (id={actor.id})"
        if actor is not None
        else f"<anonymous {request.client.host if request.client else 'unknown'}>"
    )
    row = AuditLog(
        actor_user_id=actor.id if actor is not None else None,
        actor_label=label,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        ip_address=request.client.host if request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:255] or None,
        request_id=get_request_id(),
        changes_json=changes,
    )
    db.add(row)
    db.flush()
    logger.info(
        "audit action=%s target=%s/%s actor=%s",
        action, target_type or "-", target_id or "-", label,
    )
    return row
