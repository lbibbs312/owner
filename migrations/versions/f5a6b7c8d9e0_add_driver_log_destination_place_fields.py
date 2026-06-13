"""Add destination place fields to driver logs

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-06-13 20:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def _columns(table):
    return {col["name"] for col in inspect(op.get_bind()).get_columns(table)}


def upgrade():
    existing = _columns("driver_log")
    if "destination_place_name" not in existing:
        op.add_column("driver_log", sa.Column("destination_place_name", sa.String(length=200), nullable=True))
    if "destination_lat" not in existing:
        op.add_column("driver_log", sa.Column("destination_lat", sa.Float(), nullable=True))
    if "destination_lng" not in existing:
        op.add_column("driver_log", sa.Column("destination_lng", sa.Float(), nullable=True))
    if "destination_place_id" not in existing:
        op.add_column("driver_log", sa.Column("destination_place_id", sa.String(length=255), nullable=True))
    if "destination_source" not in existing:
        op.add_column("driver_log", sa.Column("destination_source", sa.String(length=32), nullable=True))
    if "destination_confirmed" not in existing:
        op.add_column(
            "driver_log",
            sa.Column("destination_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade():
    existing = _columns("driver_log")
    for column in (
        "destination_confirmed",
        "destination_source",
        "destination_place_id",
        "destination_lng",
        "destination_lat",
        "destination_place_name",
    ):
        if column in existing:
            op.drop_column("driver_log", column)
