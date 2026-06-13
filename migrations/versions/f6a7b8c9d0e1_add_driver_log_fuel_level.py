"""Add fuel level to driver logs

Revision ID: f6a7b8c9d0e1
Revises: f5a6b7c8d9e0
Create Date: 2026-06-13 22:15:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "f6a7b8c9d0e1"
down_revision = "f5a6b7c8d9e0"
branch_labels = None
depends_on = None


def _has_column(table_name, column_name):
    return column_name in {column["name"] for column in inspect(op.get_bind()).get_columns(table_name)}


def upgrade():
    if not _has_column("driver_log", "fuel_level"):
        op.add_column("driver_log", sa.Column("fuel_level", sa.String(length=20), nullable=True))


def downgrade():
    if _has_column("driver_log", "fuel_level"):
        op.drop_column("driver_log", "fuel_level")
