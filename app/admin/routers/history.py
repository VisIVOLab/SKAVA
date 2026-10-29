# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""Audit history viewer (Phase 3) — read-only browser of ``audit_log``.

The audit log is append-only; this router never mutates it. It supports
filter-by-actor / filter-by-action / filter-by-date-range plus a single
detail page (full changes_json pretty-printed) and a CSV export of the
current filter.

CSV export streams via :func:`app.admin.csv_export.stream_csv` so a
many-million-row export does not balloon the worker's memory.
"""
from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin.auth.session import current_user_required
from app.admin.csv_export import stream_csv
from app.admin.templating import render
from app.db import get_db
from app.models.audit_log import AuditLog
from app.models.user import User

router = APIRouter(prefix="/history", tags=["admin-history"])

_PAGE_SIZE = 50
_EXPORT_LIMIT = 100_000   # hard cap so a curl-loop can't export the universe


def _parse_iso_date(raw: str | None) -> datetime | None:
    """Parse ``YYYY-MM-DD`` (date input) into a UTC midnight datetime."""
    if not raw:
        return None
    try:
        return datetime.combine(
            datetime.strptime(raw, "%Y-%m-%d").date(),
            time.min,
            tzinfo=timezone.utc,
        )
    except ValueError:
        return None


def _apply_filters(
    stmt,
    *,
    q: str,
    action_prefix: str,
    target_type: str,
    actor: str,
    since: datetime | None,
    until: datetime | None,
):
    """Apply the shared filter set to either the list query or the count.

    Returning the modified statement keeps the two callers (list + count
    + CSV) in lockstep — a filter change in one place can't drift from
    the others.
    """
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            (AuditLog.target_id.ilike(like))
            | (AuditLog.action.ilike(like))
        )
    if action_prefix:
        stmt = stmt.where(AuditLog.action.like(f"{action_prefix}%"))
    if target_type:
        stmt = stmt.where(AuditLog.target_type == target_type)
    if actor:
        stmt = stmt.where(AuditLog.actor_label.ilike(f"%{actor.strip()}%"))
    if since is not None:
        stmt = stmt.where(AuditLog.occurred_at >= since)
    if until is not None:
        # ``until`` is treated as the END of the chosen day, i.e. < next day.
        end_exclusive = until.replace(hour=0, minute=0, second=0, microsecond=0)
        from datetime import timedelta
        stmt = stmt.where(AuditLog.occurred_at < end_exclusive + timedelta(days=1))
    return stmt


def _distinct_facets(db: Session) -> tuple[list[str], list[str], list[str]]:
    """Return (target_types, action_prefixes, actors) for the filter dropdowns."""
    target_types = [
        t for (t,) in db.execute(
            select(AuditLog.target_type)
            .where(AuditLog.target_type.is_not(None))
            .distinct()
            .order_by(AuditLog.target_type)
        ).all()
    ]
    # Action prefix = part before the first dot, e.g. "node.create" → "node".
    actions = [
        a for (a,) in db.execute(
            select(AuditLog.action).distinct().order_by(AuditLog.action)
        ).all()
    ]
    prefixes = sorted({a.split(".", 1)[0] for a in actions if a})
    actors = [
        u for (u,) in db.execute(
            select(AuditLog.actor_label).distinct().order_by(AuditLog.actor_label)
        ).all()
    ]
    return target_types, prefixes, actors


@router.get("/")
def list_history(
    request: Request,
    user: Annotated[User, Depends(current_user_required)],
    db: Annotated[Session, Depends(get_db)],
    q: str = "",
    action_prefix: str = "",
    target_type: str = "",
    actor: str = "",
    since: str = "",
    until: str = "",
    page: int = 1,
):
    page = max(1, page)
    since_dt = _parse_iso_date(since)
    until_dt = _parse_iso_date(until)

    base = select(AuditLog).order_by(AuditLog.occurred_at.desc())
    count = select(func.count(AuditLog.id))

    filter_kwargs = dict(
        q=q, action_prefix=action_prefix, target_type=target_type,
        actor=actor, since=since_dt, until=until_dt,
    )
    stmt = _apply_filters(base, **filter_kwargs)
    count_stmt = _apply_filters(count, **filter_kwargs)

    total = db.scalar(count_stmt) or 0
    n_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    rows = list(db.scalars(
        stmt.offset((page - 1) * _PAGE_SIZE).limit(_PAGE_SIZE)
    ))

    target_types, prefixes, actors = _distinct_facets(db)

    # Build the "export current filter as CSV" link by passing the same
    # filter query params through (so the export matches what the user
    # is looking at, not the entire table).
    export_qs = "&".join(
        f"{k}={v}" for k, v in {
            "q": q, "action_prefix": action_prefix, "target_type": target_type,
            "actor": actor, "since": since, "until": until,
        }.items() if v
    )

    return render(
        request,
        "history/list.html",
        {
            "current_user": user,
            "rows": rows,
            "total": total,
            "page": page,
            "n_pages": n_pages,
            "q": q,
            "action_prefix": action_prefix,
            "target_type": target_type,
            "actor": actor,
            "since": since,
            "until": until,
            "target_types": target_types,
            "action_prefixes": prefixes,
            "actors": actors,
            "export_qs": export_qs,
            "export_limit": _EXPORT_LIMIT,
        },
    )


@router.get("/export.csv")
def export_history(
    user: Annotated[User, Depends(current_user_required)],
    db: Annotated[Session, Depends(get_db)],
    q: str = "",
    action_prefix: str = "",
    target_type: str = "",
    actor: str = "",
    since: str = "",
    until: str = "",
    limit: int = Query(_EXPORT_LIMIT, ge=1, le=_EXPORT_LIMIT),
):
    """Stream the filtered audit log as CSV.

    The filter set mirrors the list view 1:1 — same params, same semantics —
    so the operator's mental model is "what I see is what I download".

    Capped at ``_EXPORT_LIMIT`` rows defensively: even at ~150 bytes/row
    that's still a 15 MB file, which is the upper end of what most ops
    folks want to load into a spreadsheet for review.
    """
    since_dt = _parse_iso_date(since)
    until_dt = _parse_iso_date(until)
    stmt = _apply_filters(
        select(AuditLog).order_by(AuditLog.occurred_at.desc()),
        q=q, action_prefix=action_prefix, target_type=target_type,
        actor=actor, since=since_dt, until=until_dt,
    ).limit(limit)

    def _rows():
        for row in db.scalars(stmt):
            yield (
                row.occurred_at,
                row.actor_label,
                row.action,
                row.target_type or "",
                row.target_id or "",
                row.ip_address or "",
                row.request_id or "",
                row.changes_json,
            )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return stream_csv(
        header=[
            "occurred_at", "actor", "action", "target_type",
            "target_id", "ip_address", "request_id", "changes_json",
        ],
        rows=_rows(),
        filename=f"skava-audit-{stamp}.csv",
    )


@router.get("/{audit_id}")
def detail(
    audit_id: int,
    request: Request,
    user: Annotated[User, Depends(current_user_required)],
    db: Annotated[Session, Depends(get_db)],
):
    row = db.get(AuditLog, audit_id)
    if row is None:
        raise HTTPException(404, "Audit entry not found.")
    return render(
        request,
        "history/detail.html",
        {"current_user": user, "row": row},
    )
