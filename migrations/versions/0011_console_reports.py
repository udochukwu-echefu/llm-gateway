"""Scope/time seek and request-timeline indexes for the metadata console."""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("team_limits", sa.Column("budget_display", sa.String(32), nullable=True))
    op.execute(
        "CREATE INDEX ix_usage_org_created_id ON usage_records "
        "(organization_id, created_at DESC, id DESC)"
    )
    op.create_index(
        "ix_usage_org_request_attempt",
        "usage_records",
        ["organization_id", "request_id", "attempt"],
    )
    op.create_index("ix_usage_key_created", "usage_records", ["key_id", "created_at"])


def downgrade() -> None:
    op.drop_column("team_limits", "budget_display")
    for name in ("ix_usage_key_created", "ix_usage_org_request_attempt", "ix_usage_org_created_id"):
        op.drop_index(name, table_name="usage_records")
