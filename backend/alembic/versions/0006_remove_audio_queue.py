"""Remove Wikimedia pronunciation download queue fields.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

QUEUE_COLUMNS = (
    "audio_source_url",
    "audio_status",
    "audio_attempts",
    "audio_next_attempt_at",
    "audio_error",
)


def upgrade():
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("words")}
    with op.batch_alter_table("words") as batch_op:
        for name in QUEUE_COLUMNS:
            if name in existing:
                batch_op.drop_column(name)


def downgrade():
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("words")}
    columns = (
        sa.Column("audio_source_url", sa.String(2048), nullable=True),
        sa.Column("audio_status", sa.String(16), nullable=True),
        sa.Column("audio_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("audio_next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("audio_error", sa.String(255), nullable=True),
    )
    with op.batch_alter_table("words") as batch_op:
        for column in columns:
            if column.name not in existing:
                batch_op.add_column(column)
