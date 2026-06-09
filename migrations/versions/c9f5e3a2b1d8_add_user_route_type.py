"""Add user.route_type for the day-driver route classification

Revision ID: c9f5e3a2b1d8
Revises: b8e4d2f1a6c7
Create Date: 2026-06-09 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "c9f5e3a2b1d8"
down_revision = "b8e4d2f1a6c7"
branch_labels = None
depends_on = None


def _column_names(table_name):
    return {column["name"] for column in inspect(op.get_bind()).get_columns(table_name)}


def upgrade():
    user_columns = _column_names("user")
    with op.batch_alter_table("user", schema=None) as batch_op:
        if "route_type" not in user_columns:
            batch_op.add_column(sa.Column("route_type", sa.String(length=30), nullable=True))


def downgrade():
    user_columns = _column_names("user")
    with op.batch_alter_table("user", schema=None) as batch_op:
        if "route_type" in user_columns:
            batch_op.drop_column("route_type")
