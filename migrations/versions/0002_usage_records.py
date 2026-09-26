"""Add durable per-request usage accounting.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usage_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column("team_id", UUID(as_uuid=True), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("key_id", sa.String(12), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(256), nullable=False),
        sa.Column("endpoint", sa.String(16), nullable=False),
        sa.Column("stream", sa.Boolean, nullable=False),
        sa.Column("status_code", sa.Integer, nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("cost_status", sa.String(32), nullable=False),
        sa.Column("prompt_tokens", sa.Integer),
        sa.Column("completion_tokens", sa.Integer),
        sa.Column("cached_tokens", sa.Integer),
        sa.Column("reasoning_tokens", sa.Integer),
        sa.Column("cost_usd", sa.Numeric(20, 12)),
        sa.Column("catalog_version", sa.String(64), nullable=False),
        sa.Column("duration_ms", sa.Float),
        sa.Column("ttfb_ms", sa.Float),
    )
    op.create_index("ix_usage_org_time", "usage_records", ["organization_id", "created_at"])
    op.create_index("ix_usage_team_time", "usage_records", ["team_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_usage_team_time", table_name="usage_records")
    op.drop_index("ix_usage_org_time", table_name="usage_records")
    op.drop_table("usage_records")
