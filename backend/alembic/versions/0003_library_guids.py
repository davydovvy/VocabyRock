"""Give words and packs stable identities for vocabulary archives.

Revision ID: 0003
Revises: 0002
"""

from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    for table in ("words", "packs"):
        inspector = sa.inspect(connection)
        if "guid" not in {column["name"] for column in inspector.get_columns(table)}:
            op.add_column(table, sa.Column("guid", sa.String(36), nullable=True))
        for (row_id,) in connection.execute(sa.text(f"SELECT id FROM {table} WHERE guid IS NULL")):
            connection.execute(
                sa.text(f"UPDATE {table} SET guid = :guid WHERE id = :id"),
                {"guid": str(uuid4()), "id": row_id},
            )
        if f"ix_{table}_guid" not in {
            index["name"] for index in sa.inspect(connection).get_indexes(table)
        }:
            op.create_index(f"ix_{table}_guid", table, ["guid"], unique=True)


def downgrade():
    for table in ("packs", "words"):
        op.drop_index(f"ix_{table}_guid", table_name=table)
        op.drop_column(table, "guid")
