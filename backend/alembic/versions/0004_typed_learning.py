"""Track exact English typing separately from practice scheduling.

Revision ID: 0004
Revises: 0003
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("progress")}
    if "typed_streak" not in columns:
        op.add_column(
            "progress", sa.Column("typed_streak", sa.Integer(), nullable=False, server_default="0")
        )
    if "learned" not in columns:
        op.add_column(
            "progress",
            sa.Column("learned", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade():
    op.drop_column("progress", "learned")
    op.drop_column("progress", "typed_streak")
