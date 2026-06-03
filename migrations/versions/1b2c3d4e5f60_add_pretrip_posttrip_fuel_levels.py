"""Add PreTrip and PostTrip fuel levels

Revision ID: 1b2c3d4e5f60
Revises: 0a1b2c3d4e5f
Create Date: 2026-06-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "1b2c3d4e5f60"
down_revision = "0a1b2c3d4e5f"
branch_labels = None
depends_on = None


def _has_column(table_name, column_name):
    return column_name in {column["name"] for column in inspect(op.get_bind()).get_columns(table_name)}


def upgrade():
    if not _has_column("pretrip", "start_fuel_level"):
        with op.batch_alter_table("pretrip", schema=None) as batch_op:
            batch_op.add_column(sa.Column("start_fuel_level", sa.String(length=20), nullable=True))

    if not _has_column("posttrip", "end_fuel_level"):
        with op.batch_alter_table("posttrip", schema=None) as batch_op:
            batch_op.add_column(sa.Column("end_fuel_level", sa.String(length=20), nullable=True))


def downgrade():
    if _has_column("posttrip", "end_fuel_level"):
        with op.batch_alter_table("posttrip", schema=None) as batch_op:
            batch_op.drop_column("end_fuel_level")

    if _has_column("pretrip", "start_fuel_level"):
        with op.batch_alter_table("pretrip", schema=None) as batch_op:
            batch_op.drop_column("start_fuel_level")
