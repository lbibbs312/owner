"""Add day-driver commodity/weight fields and user day_driver flag

Revision ID: a7d3c1e9f042
Revises: 5f60718293a4
Create Date: 2026-06-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "a7d3c1e9f042"
down_revision = "5f60718293a4"
branch_labels = None
depends_on = None


def _column_names(table_name):
    return {column["name"] for column in inspect(op.get_bind()).get_columns(table_name)}


def upgrade():
    driver_log_columns = _column_names("driver_log")
    with op.batch_alter_table("driver_log", schema=None) as batch_op:
        if "commodity" not in driver_log_columns:
            batch_op.add_column(sa.Column("commodity", sa.String(length=120), nullable=True))
        if "weight" not in driver_log_columns:
            batch_op.add_column(sa.Column("weight", sa.String(length=40), nullable=True))

    user_columns = _column_names("user")
    with op.batch_alter_table("user", schema=None) as batch_op:
        if "day_driver" not in user_columns:
            batch_op.add_column(sa.Column("day_driver", sa.Boolean(), nullable=True))


def downgrade():
    user_columns = _column_names("user")
    with op.batch_alter_table("user", schema=None) as batch_op:
        if "day_driver" in user_columns:
            batch_op.drop_column("day_driver")

    driver_log_columns = _column_names("driver_log")
    with op.batch_alter_table("driver_log", schema=None) as batch_op:
        if "weight" in driver_log_columns:
            batch_op.drop_column("weight")
        if "commodity" in driver_log_columns:
            batch_op.drop_column("commodity")
