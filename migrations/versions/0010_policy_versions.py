"""Per-level policy revisions protect against repeated writes and ABA conflicts."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("organizations", "teams"):
        for policy in ("model_patterns", "guardrail_actions", "allowed_regions"):
            op.add_column(
                table,
                sa.Column(
                    policy + "_revision", sa.BigInteger(), nullable=False, server_default="0"
                ),
            )


def downgrade() -> None:
    for table in ("organizations", "teams"):
        for policy in ("model_patterns", "guardrail_actions", "allowed_regions"):
            op.drop_column(table, policy + "_revision")
