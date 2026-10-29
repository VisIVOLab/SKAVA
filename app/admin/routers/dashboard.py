# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""Dashboard — the admin landing page.

Phase 3 rebuilds this into a real metrics overview:

* Total counts of each core entity (datasets, nodes, users, audit rows)
* 7-day trend: new datasets per day, audit rows per day
* Top-5 most active actors over the last 7 days
* Top-5 actions by frequency
* Per-node dataset count (joined via DatasetReplica)
* Last 10 audit entries (link to full history viewer)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
from app.models.replica import DatasetReplica
from app.models.user import User

router = APIRouter()


def _per_day_counts(
    db: Session, since: datetime, *, column,
) -> list[tuple[str, int]]:
    """Group rows by ``date(column)`` since ``since`` and return ``[(YYYY-MM-DD, n)]``.

    Uses ``func.date()`` to bucket — portable across SQLite / Postgres
    without timezone gymnastics, since both treat the input as the
    timestamp column's storage tz (we store UTC).
    """
    bucket = func.date(column).label("d")
    rows = db.execute(
        select(bucket, func.count())
        .where(column >= since)
        .group_by(bucket)
        .order_by(bucket)
    ).all()
    return [(str(d), int(n)) for d, n in rows]


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

    # 7-day window for the trend / top-K sections. Boundaries are
    # UTC-midnight 7 days ago to keep the buckets stable as time
    # advances within the current day.
    week_ago = (
        datetime.now(timezone.utc)
        .replace(hour=0, minute=0, second=0, microsecond=0)
        - timedelta(days=6)
    )

    audit_per_day = _per_day_counts(db, week_ago, column=AuditLog.occurred_at)
    datasets_per_day = _per_day_counts(db, week_ago, column=Dataset.created_at) \
        if hasattr(Dataset, "created_at") else []

    top_actors = list(db.execute(
        select(AuditLog.actor_label, func.count())
        .where(AuditLog.occurred_at >= week_ago)
        .group_by(AuditLog.actor_label)
        .order_by(func.count().desc())
        .limit(5)
    ).all())
    top_actions = list(db.execute(
        select(AuditLog.action, func.count())
        .where(AuditLog.occurred_at >= week_ago)
        .group_by(AuditLog.action)
        .order_by(func.count().desc())
        .limit(5)
    ).all())

    # Per-node dataset counts via DatasetReplica (a dataset can be
    # replicated to multiple nodes; we count distinct datasets per node).
    per_node_rows = db.execute(
        select(Node.code, func.count(func.distinct(DatasetReplica.dataset_id)))
        .join(DatasetReplica, DatasetReplica.node_id == Node.id, isouter=True)
        .group_by(Node.code)
        .order_by(Node.code)
    ).all()
    per_node = [(code, int(n)) for code, n in per_node_rows]

    return render(
        request,
        "dashboard.html",
        {
            "current_user": user,
            "counts": counts,
            "recent_audit": recent_audit,
            "audit_per_day": audit_per_day,
            "datasets_per_day": datasets_per_day,
            "top_actors": top_actors,
            "top_actions": top_actions,
            "per_node": per_node,
            "window_days": 7,
        },
    )
