"""Team-specific limits, nullable to inherit global defaults.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "team_limits",
        sa.Column("team_id", UUID(as_uuid=True), sa.ForeignKey("teams.id"), primary_key=True),
        sa.Column("rpm", sa.Integer),
        sa.Column("tpm", sa.Integer),
        sa.Column("max_concurrency", sa.Integer),
        sa.Column("monthly_budget_usd", sa.Numeric(20, 12)),
        sa.Column("alert_threshold", sa.Numeric(4, 3)),
    )


def downgrade() -> None:
    op.drop_table("team_limits")
