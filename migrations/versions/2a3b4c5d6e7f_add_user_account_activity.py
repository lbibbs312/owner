"""Add user account activity timestamps

Revision ID: 2a3b4c5d6e7f
Revises: 1f2e3d4c5b6a
Create Date: 2026-06-16 15:05:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "2a3b4c5d6e7f"
down_revision = "1f2e3d4c5b6a"
branch_labels = None
depends_on = None


def _has_table(table_name):
    return inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name, column_name):
    return column_name in {column["name"] for column in inspect(op.get_bind()).get_columns(table_name)}


def upgrade():
    if not _has_table("user"):
        return
    with op.batch_alter_table("user") as batch_op:
        if not _has_column("user", "created_at"):
            batch_op.add_column(sa.Column("created_at", sa.DateTime(), nullable=True))
        if not _has_column("user", "last_login_at"):
            batch_op.add_column(sa.Column("last_login_at", sa.DateTime(), nullable=True))
    op.execute(sa.text('UPDATE "user" SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL'))


def downgrade():
    if not _has_table("user"):
        return
    with op.batch_alter_table("user") as batch_op:
        if _has_column("user", "last_login_at"):
            batch_op.drop_column("last_login_at")
        if _has_column("user", "created_at"):
            batch_op.drop_column("created_at")
