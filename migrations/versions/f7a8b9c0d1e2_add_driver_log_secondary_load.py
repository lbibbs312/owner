"""Add secondary load to driver logs

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-05-15 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def _column_names(table_name):
    return {column["name"] for column in inspect(op.get_bind()).get_columns(table_name)}


def upgrade():
    if "secondary_load" not in _column_names("driver_log"):
        op.add_column("driver_log", sa.Column("secondary_load", sa.String(length=80), nullable=True))


def downgrade():
    if "secondary_load" in _column_names("driver_log"):
        op.drop_column("driver_log", "secondary_load")
