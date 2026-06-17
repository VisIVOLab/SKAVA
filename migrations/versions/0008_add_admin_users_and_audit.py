"""Add admin users + audit_log tables.

Phase 1 of the SKAVA Admin UI (production-grade — see
``app/admin/README.md``). Introduces:

* ``users``      — local username+bcrypt accounts with role enum.
                    OIDC accounts will be linked here via a future
                    ``oidc_subject`` column.
* ``audit_log``  — append-only record of mutating actions performed
                    through the admin UI or internal API. Used for
                    forensics, compliance and the admin Audit page.

The schema is intentionally minimal at this stage: enough to enforce
RBAC and tell who-changed-what-when, without committing to a particular
SSO or RBAC system.
"""

import sqlalchemy as sa
from alembic import op


revision = "0008_add_admin_users_and_audit"
down_revision = "0007_add_visivo_backend"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── users ──────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("email", sa.String(256), nullable=True, unique=True),
        sa.Column("full_name", sa.String(256), nullable=True),
        # ``role`` is a string column (not a pg ENUM) so we can add new
        # roles in code without an enum-altering migration. Allowed
        # values are validated by the Pydantic UserRole on the way in.
        sa.Column(
            "role",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'viewer'"),
        ),
        sa.Column(
            "password_hash",
            sa.String(255),
            nullable=True,
            comment="bcrypt; nullable for SSO-only accounts (future).",
        ),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── audit_log ──────────────────────────────────────────────────────
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            index=True,
        ),
        sa.Column(
            "actor_user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
            comment="NULL when the action was performed by a system "
                    "process or an internal-API client.",
        ),
        sa.Column("actor_label", sa.String(128), nullable=False,
                   comment="Display label captured at write time so audit "
                           "rows stay readable even if the user is renamed "
                           "or deleted later."),
        sa.Column("action", sa.String(64), nullable=False, index=True,
                   comment="Dot-separated verb path, e.g. dataset.create, "
                           "node.delete, user.role_change."),
        sa.Column("target_type", sa.String(32), nullable=True, index=True,
                   comment="Entity class: dataset|node|user|ingestion_job."),
        sa.Column("target_id", sa.String(64), nullable=True, index=True),
        sa.Column("ip_address", sa.String(45), nullable=True,
                   comment="IPv4 or IPv6 of the request origin."),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True, index=True,
                   comment="Mirrors RequestContextMiddleware.request_id "
                           "for cross-log correlation."),
        sa.Column(
            "changes_json",
            sa.JSON,
            nullable=True,
            comment="Optional structured diff: "
                    "{'before': {...}, 'after': {...}}. NULL for "
                    "read-only audited actions (e.g. login).",
        ),
    )

    # ── Trigger to bump users.updated_at automatically on UPDATE ───────
    # Using a portable approach: set updated_at = NOW() in the model
    # layer's ``onupdate=`` would be cleaner, but we add a DB trigger so
    # external admin queries (psql, dbeaver) also update it. Postgres
    # only; SQLite (used by tests) skips the trigger.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION users_set_updated_at()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_users_updated_at
            BEFORE UPDATE ON users
            FOR EACH ROW EXECUTE FUNCTION users_set_updated_at();
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_users_updated_at ON users;")
        op.execute("DROP FUNCTION IF EXISTS users_set_updated_at();")
    op.drop_table("audit_log")
    op.drop_table("users")
