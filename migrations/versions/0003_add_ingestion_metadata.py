"""add ingestion metadata fields

Revision ID: 0003_add_ingestion_metadata
Revises: 0002_add_search_indexes
Create Date: 2026-03-18
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_add_ingestion_metadata"
down_revision = "0002_add_search_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("datasets", sa.Column("access_format", sa.String(length=128), nullable=True))
    op.add_column("datasets", sa.Column("access_estsize", sa.Integer(), nullable=True))
    op.add_column("datasets", sa.Column("ingested_at", sa.DateTime(), nullable=True))
    op.add_column("datasets", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.add_column("datasets", sa.Column("source_type", sa.String(length=64), nullable=True))
    op.add_column("datasets", sa.Column("source_ref", sa.String(length=256), nullable=True))
    op.add_column("datasets", sa.Column("checksum", sa.String(length=128), nullable=True))

    op.add_column(
        "dataset_replicas",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="available"),
    )
    op.add_column(
        "dataset_replicas",
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("dataset_replicas", "is_public")
    op.drop_column("dataset_replicas", "status")

    op.drop_column("datasets", "checksum")
    op.drop_column("datasets", "source_ref")
    op.drop_column("datasets", "source_type")
    op.drop_column("datasets", "updated_at")
    op.drop_column("datasets", "ingested_at")
    op.drop_column("datasets", "access_estsize")
    op.drop_column("datasets", "access_format")
