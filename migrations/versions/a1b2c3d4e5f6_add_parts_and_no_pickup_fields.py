"""Add task/log parts and no-pickup fields

Revision ID: a1b2c3d4e5f6
Revises: 9d2e4f6a8b10
Create Date: 2026-05-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "a1b2c3d4e5f6"
down_revision = "9d2e4f6a8b10"
branch_labels = None
depends_on = None


def _column_names(table_name):
    return {column["name"] for column in inspect(op.get_bind()).get_columns(table_name)}


def upgrade():
    task_columns = _column_names("task")
    with op.batch_alter_table("task", schema=None) as batch_op:
        if "part_number" not in task_columns:
            batch_op.add_column(sa.Column("part_number", sa.String(length=80), nullable=True))

    driver_log_columns = _column_names("driver_log")
    with op.batch_alter_table("driver_log", schema=None) as batch_op:
        if "part_number" not in driver_log_columns:
            batch_op.add_column(sa.Column("part_number", sa.String(length=80), nullable=True))
        if "hot_parts" not in driver_log_columns:
            batch_op.add_column(sa.Column("hot_parts", sa.Boolean(), nullable=True))
        if "no_pickup" not in driver_log_columns:
            batch_op.add_column(sa.Column("no_pickup", sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table("driver_log", schema=None) as batch_op:
        batch_op.drop_column("no_pickup")
        batch_op.drop_column("hot_parts")
        batch_op.drop_column("part_number")

    with op.batch_alter_table("task", schema=None) as batch_op:
        batch_op.drop_column("part_number")
