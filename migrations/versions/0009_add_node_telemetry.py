# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""Add measured node state (telemetry) to the nodes table

SKAVA probes each node's co-located VisIVO backend (``/v1/ping`` for the round
trip, ``/v1/node/status`` for capacity) and the resource-aware ranking policy
reads the result, so routing follows what the nodes can take on now rather
than scores declared at registration.

Revision ID: 0009_add_node_telemetry
Revises: 0008_add_admin_users_and_audit
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_add_node_telemetry"
down_revision = "0008_add_admin_users_and_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("nodes", sa.Column("probe_ok", sa.Boolean(), nullable=True))
    op.add_column("nodes", sa.Column("probe_rtt_ms", sa.Float(), nullable=True))
    op.add_column("nodes", sa.Column("probe_error", sa.String(256), nullable=True))
    op.add_column("nodes", sa.Column("telemetry_json", sa.JSON(), nullable=True))
    op.add_column("nodes", sa.Column("telemetry_at", sa.DateTime(timezone=False), nullable=True))


def downgrade() -> None:
    for column in ("telemetry_at", "telemetry_json", "probe_error", "probe_rtt_ms", "probe_ok"):
        op.drop_column("nodes", column)
