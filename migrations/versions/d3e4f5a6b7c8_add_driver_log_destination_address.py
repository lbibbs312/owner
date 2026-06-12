"""Add destination address to driver logs

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-06-11 20:10:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "d3e4f5a6b7c8"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def _columns(table):
    return {col["name"] for col in inspect(op.get_bind()).get_columns(table)}


def upgrade():
    if "destination_address" not in _columns("driver_log"):
        op.add_column("driver_log", sa.Column("destination_address", sa.String(length=255), nullable=True))


def downgrade():
    if "destination_address" in _columns("driver_log"):
        op.drop_column("driver_log", "destination_address")
