"""Read-only admin credentials with optional organization scope."""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

ADMIN_SCOPE = (
    "(role = 'platform' AND organization_id IS NULL) OR "
    "(role = 'org' AND organization_id IS NOT NULL)"
)


def upgrade() -> None:
    op.drop_constraint("admin_key_scope", "admin_keys", type_="check")
    op.create_check_constraint("admin_key_scope", "admin_keys", ADMIN_SCOPE + " OR role = 'viewer'")


def downgrade() -> None:
    # Serialize with key issuance so a viewer cannot appear between the check and DDL.
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE admin_keys IN ACCESS EXCLUSIVE MODE"))
    if connection.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM admin_keys WHERE role = 'viewer')")):
        raise RuntimeError(
            "Cannot downgrade 0012 while viewer keys exist, including revoked keys. "
            "Explicitly remove viewer rows after reviewing their audit history."
        )
    op.drop_constraint("admin_key_scope", "admin_keys", type_="check")
    op.create_check_constraint("admin_key_scope", "admin_keys", ADMIN_SCOPE)
