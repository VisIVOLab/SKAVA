"""add ingestion jobs table

Revision ID: 0004_add_ingestion_jobs
Revises: 0003_add_ingestion_metadata
Create Date: 2026-03-18
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_add_ingestion_jobs"
down_revision = "0003_add_ingestion_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=True),
        sa.Column("source_ref", sa.String(length=256), nullable=True),
        sa.Column("filename", sa.String(length=512), nullable=True),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("triggered_by", sa.String(length=128), nullable=True),
    )
    op.create_index("ix_ingestion_jobs_status", "ingestion_jobs", ["status"], unique=False)

    # DB-backed single-job execution control across instances.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_ingestion_jobs_single_running "
        "ON ingestion_jobs(status) WHERE status = 'running'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_ingestion_jobs_single_running")
    op.drop_index("ix_ingestion_jobs_status", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
