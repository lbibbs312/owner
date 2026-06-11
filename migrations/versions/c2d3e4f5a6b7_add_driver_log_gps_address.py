"""Add GPS address capture to driver logs

Revision ID: c2d3e4f5a6b7
Revises: b8c9d0e1f2a3
Create Date: 2026-06-11 15:35:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "c2d3e4f5a6b7"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def _columns(table):
    return {col["name"] for col in inspect(op.get_bind()).get_columns(table)}


def upgrade():
    columns = _columns("driver_log")
    if "location_address" not in columns:
        op.add_column("driver_log", sa.Column("location_address", sa.String(length=255), nullable=True))
    if "gps_latitude" not in columns:
        op.add_column("driver_log", sa.Column("gps_latitude", sa.Float(), nullable=True))
    if "gps_longitude" not in columns:
        op.add_column("driver_log", sa.Column("gps_longitude", sa.Float(), nullable=True))
    if "gps_accuracy_m" not in columns:
        op.add_column("driver_log", sa.Column("gps_accuracy_m", sa.Float(), nullable=True))


def downgrade():
    columns = _columns("driver_log")
    if "gps_accuracy_m" in columns:
        op.drop_column("driver_log", "gps_accuracy_m")
    if "gps_longitude" in columns:
        op.drop_column("driver_log", "gps_longitude")
    if "gps_latitude" in columns:
        op.drop_column("driver_log", "gps_latitude")
    if "location_address" in columns:
        op.drop_column("driver_log", "location_address")
