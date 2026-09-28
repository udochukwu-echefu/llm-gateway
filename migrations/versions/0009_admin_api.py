"""Admin credentials, retry records and least-privilege reporting role."""

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key_id", sa.String(12), nullable=False, unique=True),
        sa.Column("secret_hash", sa.LargeBinary(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column(
            "organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id")
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "(role = 'platform' AND organization_id IS NULL) OR "
            "(role = 'org' AND organization_id IS NOT NULL)",
            name="admin_key_scope",
        ),
    )
    op.create_index("ix_admin_keys_key_id", "admin_keys", ["key_id"])
    op.create_table(
        "admin_idempotency",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor", sa.String(32), nullable=False),
        sa.Column("route", sa.String(256), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response", postgresql.JSONB(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("actor", "route", "token_hash"),
    )
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "DO $$ BEGIN CREATE ROLE gateway_readonly; "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
        )
    )
    connection.execute(sa.text("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM gateway_readonly"))
    connection.execute(
        sa.text(
            "CREATE VIEW usage_team_budgets AS SELECT team_id, monthly_budget_usd FROM team_limits"
        )
    )
    connection.execute(sa.text("GRANT USAGE ON SCHEMA public TO gateway_readonly"))
    connection.execute(
        sa.text(
            "GRANT SELECT ON organizations, teams, usage_records, "
            "usage_team_budgets TO gateway_readonly"
        )
    )
    password = os.getenv("GATEWAY_READONLY_DB_PASSWORD")
    if password:
        connection.execute(
            sa.text("SELECT set_config('gateway.readonly_password', :password, true)"),
            {"password": password},
        )
        connection.execute(
            sa.text(
                "DO $$ BEGIN EXECUTE format('ALTER ROLE gateway_readonly "
                "LOGIN PASSWORD %L', current_setting('gateway.readonly_password')); END $$"
            )
        )
    else:
        connection.execute(sa.text("ALTER ROLE gateway_readonly NOLOGIN"))


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("REVOKE ALL ON usage_team_budgets FROM gateway_readonly"))
    connection.execute(sa.text("DROP VIEW usage_team_budgets"))
    connection.execute(
        sa.text("REVOKE ALL ON organizations, teams, usage_records FROM gateway_readonly")
    )
    op.drop_table("admin_idempotency")
    op.drop_index("ix_admin_keys_key_id", table_name="admin_keys")
    op.drop_table("admin_keys")
