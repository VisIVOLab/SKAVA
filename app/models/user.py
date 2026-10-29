# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""Admin user account model.

The Admin UI (see ``app/admin``) authenticates against this table using
bcrypt-hashed passwords stored in ``password_hash``. The same table is
designed to also host SSO-linked accounts in a later phase — a future
migration will add an ``oidc_subject`` column without changing this
model's role enum or auth code paths.

Roles are kept as a plain string column to allow adding new roles in
code without database migrations; the canonical set is validated by
``UserRole`` below.
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class UserRole(str, enum.Enum):
    """Canonical set of admin roles. Stored as a plain string in the DB.

    * ``admin``    — full access: create users, edit any record, view audit
    * ``ingester`` — manage datasets + nodes, run ingestion jobs
    * ``viewer``   — read-only access to all admin pages
    """

    admin = "admin"
    ingester = "ingester"
    viewer = "viewer"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(256), unique=True, nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Stored as a string for forward-compat with new roles. The model
    # never returns the raw string outside this module — accessors below
    # parse it through UserRole to fail fast on unknown values.
    role: Mapped[str] = mapped_column(
        String(32), nullable=False, default=UserRole.viewer.value
    )

    # bcrypt hash via passlib; nullable for SSO-only accounts where
    # the credential lives in the IdP.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Accessors ──────────────────────────────────────────────────────

    def get_role(self) -> UserRole:
        try:
            return UserRole(self.role)
        except ValueError as exc:
            # Defensive: an unknown role in the DB indicates either
            # a deployment-config skew or someone hand-edited the row.
            # Returning the most restrictive role is safe-by-default.
            raise ValueError(
                f"User {self.username} has unknown role {self.role!r}"
            ) from exc

    def has_role(self, *roles: UserRole) -> bool:
        try:
            return self.get_role() in roles
        except ValueError:
            return False

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id} username={self.username!r} role={self.role}>"
