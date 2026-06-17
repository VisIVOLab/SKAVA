"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-03-18
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("base_url", sa.String(length=512), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("latency_score", sa.Float(), nullable=True),
        sa.Column("load_score", sa.Float(), nullable=True),
        sa.Column("capability_score", sa.Float(), nullable=True),
    )
    op.create_index("ix_nodes_code", "nodes", ["code"], unique=True)

    op.create_table(
        "datasets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("obs_id", sa.String(length=128), nullable=False),
        sa.Column("obs_collection", sa.String(length=128), nullable=True),
        sa.Column("obs_title", sa.String(length=256), nullable=True),
        sa.Column("dataproduct_type", sa.String(length=64), nullable=True),
        sa.Column("calib_level", sa.Integer(), nullable=True),
        sa.Column("target_name", sa.String(length=128), nullable=True),
        sa.Column("facility_name", sa.String(length=128), nullable=True),
        sa.Column("instrument_name", sa.String(length=128), nullable=True),
        sa.Column("s_ra", sa.Float(), nullable=True),
        sa.Column("s_dec", sa.Float(), nullable=True),
        sa.Column("t_min", sa.Float(), nullable=True),
        sa.Column("t_max", sa.Float(), nullable=True),
        sa.Column("em_min", sa.Float(), nullable=True),
        sa.Column("em_max", sa.Float(), nullable=True),
    )
    op.create_index("ix_datasets_obs_id", "datasets", ["obs_id"], unique=True)

    op.create_table(
        "dataset_replicas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", sa.Integer(), sa.ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("remote_path", sa.String(length=512), nullable=False),
        sa.Column("access_endpoint", sa.String(length=512), nullable=False),
        sa.UniqueConstraint("dataset_id", "node_id", name="uq_dataset_node"),
    )
    op.create_index("ix_dataset_replicas_dataset_id", "dataset_replicas", ["dataset_id"], unique=False)
    op.create_index("ix_dataset_replicas_node_id", "dataset_replicas", ["node_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_dataset_replicas_node_id", table_name="dataset_replicas")
    op.drop_index("ix_dataset_replicas_dataset_id", table_name="dataset_replicas")
    op.drop_table("dataset_replicas")

    op.drop_index("ix_datasets_obs_id", table_name="datasets")
    op.drop_table("datasets")

    op.drop_index("ix_nodes_code", table_name="nodes")
    op.drop_table("nodes")
