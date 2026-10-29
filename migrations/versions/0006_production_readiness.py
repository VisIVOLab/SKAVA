# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""add production readiness metadata and job tables

Revision ID: 0006_production_readiness
Revises: 0005_scientific_query_support
Create Date: 2026-05-20
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_production_readiness"
down_revision = "0005_scientific_query_support"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("datasets", sa.Column("spatial_index_order", sa.Integer(), nullable=True))
    op.add_column("datasets", sa.Column("spatial_index_cell", sa.String(length=64), nullable=True))
    op.add_column("datasets", sa.Column("provenance_json", sa.JSON(), nullable=True))
    op.add_column("datasets", sa.Column("doi", sa.String(length=256), nullable=True))
    op.add_column("datasets", sa.Column("pid", sa.String(length=256), nullable=True))
    op.add_column("datasets", sa.Column("citation", sa.Text(), nullable=True))
    op.add_column("datasets", sa.Column("license", sa.String(length=128), nullable=True))
    op.execute("CREATE INDEX IF NOT EXISTS ix_datasets_spatial_index_order ON datasets (spatial_index_order)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_datasets_spatial_index_cell ON datasets (spatial_index_cell)")

    op.create_table(
        "tap_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("maxrec", sa.Integer(), nullable=True),
        sa.Column("format", sa.String(length=64), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("submitted_by", sa.String(length=128), nullable=True),
    )
    op.create_index("ix_tap_jobs_status", "tap_jobs", ["status"], unique=False)

    op.create_table(
        "staging_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("obs_id", sa.String(length=128), nullable=False),
        sa.Column("stage_mode", sa.String(length=32), nullable=False),
        sa.Column("staged_url", sa.String(length=512), nullable=True),
        sa.Column("request_json", sa.JSON(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.String(length=128), nullable=True),
    )
    op.create_index("ix_staging_jobs_status", "staging_jobs", ["status"], unique=False)
    op.create_index("ix_staging_jobs_obs_id", "staging_jobs", ["obs_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_staging_jobs_obs_id", table_name="staging_jobs")
    op.drop_index("ix_staging_jobs_status", table_name="staging_jobs")
    op.drop_table("staging_jobs")
    op.drop_index("ix_tap_jobs_status", table_name="tap_jobs")
    op.drop_table("tap_jobs")
    op.execute("DROP INDEX IF EXISTS ix_datasets_spatial_index_cell")
    op.execute("DROP INDEX IF EXISTS ix_datasets_spatial_index_order")
    op.drop_column("datasets", "license")
    op.drop_column("datasets", "citation")
    op.drop_column("datasets", "pid")
    op.drop_column("datasets", "doi")
    op.drop_column("datasets", "provenance_json")
    op.drop_column("datasets", "spatial_index_cell")
    op.drop_column("datasets", "spatial_index_order")
