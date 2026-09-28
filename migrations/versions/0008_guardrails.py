"""Tenant guardrails, residency and metadata-only redaction counts."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("organizations", "teams"):
        op.add_column(
            table, sa.Column("guardrail_actions", postgresql.ARRAY(sa.String()), nullable=True)
        )
        op.add_column(
            table, sa.Column("allowed_regions", postgresql.ARRAY(sa.String()), nullable=True)
        )
    op.add_column("usage_records", sa.Column("redaction_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("usage_records", "redaction_count")
    for table in ("organizations", "teams"):
        op.drop_column(table, "allowed_regions")
        op.drop_column(table, "guardrail_actions")
