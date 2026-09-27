"""Estimated savings from team-scoped response cache hits.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("usage_records", sa.Column("saved_usd", sa.Numeric(20, 12), nullable=True))


def downgrade() -> None:
    op.drop_column("usage_records", "saved_usd")
