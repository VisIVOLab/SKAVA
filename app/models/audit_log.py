"""Append-only audit log of mutating actions in the admin UI.

Every audited HTTP request writes one row here, capturing:

* who performed the action (user id + display label snapshot)
* what was changed (action verb, target type + id, before/after diff)
* when (UTC timestamp)
* from where (IP + user agent + request id)

The table is never updated or deleted from application code; retention
is handled by an external policy (cron pg_dump to cold storage + DELETE
beyond N days).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    # BIGINT in PostgreSQL (production); INTEGER under SQLite so the PK acts
    # as the rowid alias and auto-increments. A plain BIGINT PRIMARY KEY in
    # SQLite is NOT the rowid alias and would insert NULL → NOT NULL failure
    # (breaks the admin/audit tests, which run on SQLite via create_all).
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    # FK is SET NULL on user delete so audit history survives even if
    # the user is removed; the snapshot label below keeps readability.
    actor_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_label: Mapped[str] = mapped_column(String(128), nullable=False)

    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    changes_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
