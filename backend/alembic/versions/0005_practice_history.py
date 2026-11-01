"""Preserve per-question attempt history and pack names for reports.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("practice_sessions")}
    if "attempt_history" not in columns:
        op.add_column("practice_sessions", sa.Column("attempt_history", sa.JSON(), nullable=True))
    if "pack_name" not in columns:
        op.add_column("practice_sessions", sa.Column("pack_name", sa.String(100), nullable=True))
    op.execute("UPDATE practice_sessions SET attempt_history = '[]'")
    op.execute(
        "UPDATE practice_sessions SET pack_name = "
        "(SELECT name FROM packs WHERE packs.id = practice_sessions.pack_id)"
    )
    indexes = {index["name"] for index in inspector.get_indexes("practice_sessions")}
    if "ix_practice_sessions_started_at" not in indexes:
        op.create_index("ix_practice_sessions_started_at", "practice_sessions", ["started_at"])


def downgrade():
    op.drop_index("ix_practice_sessions_started_at", table_name="practice_sessions")
    op.drop_column("practice_sessions", "pack_name")
    op.drop_column("practice_sessions", "attempt_history")
