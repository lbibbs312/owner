"""Freight stop redesign: free-text destination on driver_log, and widen
plant_name so day-driver stops can hold a real location name (customer,
dock, truck stop, city) instead of a plant code.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-11 01:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def _columns(table):
    return {col["name"] for col in inspect(op.get_bind()).get_columns(table)}


def upgrade():
    bind = op.get_bind()
    if "destination" not in _columns("driver_log"):
        op.add_column("driver_log", sa.Column("destination", sa.String(length=120), nullable=True))
    if bind.dialect.name == "postgresql":
        # SQLite does not enforce VARCHAR length; Postgres does.
        op.alter_column(
            "driver_log",
            "plant_name",
            type_=sa.String(length=120),
            existing_type=sa.String(length=20),
            existing_nullable=False,
        )


def downgrade():
    bind = op.get_bind()
    if "destination" in _columns("driver_log"):
        op.drop_column("driver_log", "destination")
    if bind.dialect.name == "postgresql":
        op.alter_column(
            "driver_log",
            "plant_name",
            type_=sa.String(length=20),
            existing_type=sa.String(length=120),
            existing_nullable=False,
        )
