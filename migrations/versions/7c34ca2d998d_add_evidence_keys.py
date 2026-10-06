"""add evidence keys

Revision ID: 7c34ca2d998d
Revises: e3cb32e9cf04
Create Date: 2026-10-06 20:43:44.743710

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c34ca2d998d"
down_revision: str | Sequence[str] | None = "e3cb32e9cf04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("match_evidence", schema=None) as batch_op:
        batch_op.add_column(sa.Column("evidence_key", sa.String(length=100), nullable=True))
    op.execute("UPDATE match_evidence SET evidence_key = id WHERE evidence_key IS NULL")
    with op.batch_alter_table("match_evidence", schema=None) as batch_op:
        batch_op.alter_column("evidence_key", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("match_evidence", schema=None) as batch_op:
        batch_op.drop_column("evidence_key")
