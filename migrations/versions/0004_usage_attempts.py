"""Keep a separate receipt for every provider attempt.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "usage_records", sa.Column("attempt", sa.Integer, nullable=False, server_default="1")
    )
    op.add_column("usage_records", sa.Column("fallback_from", sa.String(300)))


def downgrade() -> None:
    op.drop_column("usage_records", "fallback_from")
    op.drop_column("usage_records", "attempt")
