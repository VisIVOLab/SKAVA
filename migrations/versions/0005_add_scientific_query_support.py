"""add scientific query support fields and indexes

Revision ID: 0005_add_scientific_query_support
Revises: 0004_add_ingestion_jobs
Create Date: 2026-03-18
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_add_scientific_query_support"
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

