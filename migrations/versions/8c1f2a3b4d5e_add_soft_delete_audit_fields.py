"""Add soft-delete audit fields

Revision ID: 8c1f2a3b4d5e
Revises: 7f3b2e91d4a6
Create Date: 2026-05-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "8c1f2a3b4d5e"
down_revision = "7f3b2e91d4a6"
branch_labels = None
depends_on = None


TABLES = ("driver_log", "pretrip", "plant_transfer")


def _has_table(table_name):
    return inspect(op.get_bind()).has_table(table_name)


def _column_names(table_name):
    return {column["name"] for column in inspect(op.get_bind()).get_columns(table_name)}


def _drop_orphan_batch_table(table_name):
    temp_table = f"_alembic_tmp_{table_name}"
    if _has_table(temp_table):
        op.drop_table(temp_table)


def upgrade():
    for table_name in TABLES:
        if not _has_table(table_name):
            continue
        _drop_orphan_batch_table(table_name)
        existing_columns = _column_names(table_name)
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            if "deleted_at" not in existing_columns:
                batch_op.add_column(sa.Column("deleted_at", sa.DateTime(), nullable=True))
            if "deleted_by_id" not in existing_columns:
                batch_op.add_column(sa.Column("deleted_by_id", sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    f"fk_{table_name}_deleted_by_id_user",
                    "user",
                    ["deleted_by_id"],
                    ["id"],
                )


def downgrade():
    for table_name in reversed(TABLES):
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            batch_op.drop_constraint(f"fk_{table_name}_deleted_by_id_user", type_="foreignkey")
            batch_op.drop_column("deleted_by_id")
            batch_op.drop_column("deleted_at")
