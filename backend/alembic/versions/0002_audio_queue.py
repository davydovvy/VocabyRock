"""Persist pronunciation download work.

Revision ID: 0002
Revises: 0001
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    # Revision 0001 creates tables from current ORM metadata on fresh installs.
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("words")}
    columns = [
        sa.Column("audio_source_url", sa.String(2048), nullable=True),
        sa.Column("audio_status", sa.String(16), nullable=True),
        sa.Column("audio_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("audio_next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("audio_error", sa.String(255), nullable=True),
    ]
    for column in columns:
        if column.name not in existing:
            op.add_column("words", column)


def downgrade():
    op.drop_column("words", "audio_error")
    op.drop_column("words", "audio_next_attempt_at")
    op.drop_column("words", "audio_attempts")
    op.drop_column("words", "audio_status")
    op.drop_column("words", "audio_source_url")
