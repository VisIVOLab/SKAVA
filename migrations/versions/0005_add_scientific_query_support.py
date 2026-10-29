# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""add scientific query support fields and indexes

Revision ID: 0005_scientific_query_support
Revises: 0004_add_ingestion_jobs
Create Date: 2026-03-18
"""

from alembic import op
import sqlalchemy as sa


# NOTE: kept to <= 32 chars — alembic_version.version_num is VARCHAR(32) and
# PostgreSQL enforces it (the old 33-char id broke `alembic upgrade` on a real
# Postgres; SQLite silently allowed it, hiding the bug in tests).
revision = "0005_scientific_query_support"
down_revision = "0004_add_ingestion_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("datasets", sa.Column("s_fov", sa.Float(), nullable=True))

    # Query acceleration for VO-style filters.
    op.execute("CREATE INDEX IF NOT EXISTS ix_datasets_s_ra ON datasets (s_ra)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_datasets_s_dec ON datasets (s_dec)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_datasets_em_min ON datasets (em_min)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_datasets_em_max ON datasets (em_max)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_datasets_t_min ON datasets (t_min)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_datasets_t_max ON datasets (t_max)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_datasets_t_max")
    op.execute("DROP INDEX IF EXISTS ix_datasets_t_min")
    op.execute("DROP INDEX IF EXISTS ix_datasets_em_max")
    op.execute("DROP INDEX IF EXISTS ix_datasets_em_min")
    op.execute("DROP INDEX IF EXISTS ix_datasets_s_dec")
    op.execute("DROP INDEX IF EXISTS ix_datasets_s_ra")
    op.drop_column("datasets", "s_fov")

