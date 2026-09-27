"""Organization/team model policies and per-attempt alias attribution.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("organizations", "teams"):
        op.add_column(table, sa.Column("model_patterns", ARRAY(sa.String), nullable=True))
    op.add_column("usage_records", sa.Column("alias", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("usage_records", "alias")
    for table in ("teams", "organizations"):
        op.drop_column(table, "model_patterns")
