"""add search indexes

Revision ID: 0002_add_search_indexes
Revises: 0001_initial
Create Date: 2026-03-18
"""

from alembic import op


revision = "0002_add_search_indexes"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Safe and idempotent index creation for production upgrades.
    op.execute("CREATE INDEX IF NOT EXISTS ix_datasets_obs_collection ON datasets (obs_collection)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_datasets_dataproduct_type ON datasets (dataproduct_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_datasets_obs_id ON datasets (obs_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_dataset_replicas_dataset_id ON dataset_replicas (dataset_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_dataset_replicas_node_id ON dataset_replicas (node_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_datasets_obs_collection")
    op.execute("DROP INDEX IF EXISTS ix_datasets_dataproduct_type")
    # Preserve compatibility with existing schemas; only drop if present.
    op.execute("DROP INDEX IF EXISTS ix_datasets_obs_id")
    op.execute("DROP INDEX IF EXISTS ix_dataset_replicas_dataset_id")
    op.execute("DROP INDEX IF EXISTS ix_dataset_replicas_node_id")
