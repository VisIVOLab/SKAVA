# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""Add VisIVO backend coordinates to nodes table

Each node may expose a co-located VisIVO backend (FastAPI service that
opens the dataset files directly from the SRC's storage filesystem,
avoiding download to the desktop client). The two columns are:

* ``visivo_backend_url`` — base URL of the VisIVO backend service at
  this node (``NULL`` when the node doesn't offer one).
* ``visivo_backend_requires_auth`` — whether the desktop client should
  send its bearer token to that backend.

The DataLink builder picks these up and surfaces them to the desktop
as ``service_descriptors[]`` entries with
``service_type == "visivo-backend"``.

See docs/distributed-backend-design.md §7 for the full design.

Revision ID: 0007_add_visivo_backend
Revises: 0006_production_readiness
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0007_add_visivo_backend"
down_revision = "0006_production_readiness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "nodes",
        sa.Column("visivo_backend_url", sa.String(256), nullable=True),
    )
    op.add_column(
        "nodes",
        sa.Column(
            "visivo_backend_requires_auth",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("nodes", "visivo_backend_requires_auth")
    op.drop_column("nodes", "visivo_backend_url")
