"""Dashboard — the admin landing page.

Phase 1 shows just enough to confirm the auth / RBAC / templating
stack is wired correctly (current user, role, last login, counts of
the three core entities). Phase 3 will rebuild this into a real
metrics overview.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin.auth.session import current_user_required
from app.admin.templating import render
from app.db import get_db
from app.models.audit_log import AuditLog
from app.models.dataset import Dataset
from app.models.node import Node
from app.models.user import User

router = APIRouter()


@router.get("/")
def index(
    request: Request,
    user: Annotated[User, Depends(current_user_required)],
    db: Annotated[Session, Depends(get_db)],
):
    counts = {
        "datasets": db.scalar(select(func.count()).select_from(Dataset)) or 0,
        "nodes": db.scalar(select(func.count()).select_from(Node)) or 0,
        "users": db.scalar(select(func.count()).select_from(User)) or 0,
        "audit_rows": db.scalar(select(func.count()).select_from(AuditLog)) or 0,
    }
    recent_audit = list(
        db.scalars(select(AuditLog).order_by(AuditLog.occurred_at.desc()).limit(10))
    )
    return render(
        request,
        "dashboard.html",
        {
            "current_user": user,
            "counts": counts,
            "recent_audit": recent_audit,
        },
    )
