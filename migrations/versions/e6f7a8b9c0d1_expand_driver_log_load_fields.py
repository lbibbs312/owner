"""Expand driver log load fields for destination loads

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-05-15 15:20:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def _column_names(table_name):
    return {column["name"] for column in inspect(op.get_bind()).get_columns(table_name)}


def upgrade():
    columns = _column_names("driver_log")
    with op.batch_alter_table("driver_log", schema=None) as batch_op:
        batch_op.alter_column(
            "load_size",
            existing_type=sa.String(length=10),
            type_=sa.String(length=80),
            existing_nullable=False,
        )
        if "depart_load_size" not in columns:
            batch_op.add_column(sa.Column("depart_load_size", sa.String(length=80), nullable=True))
        else:
            batch_op.alter_column(
                "depart_load_size",
                existing_type=sa.String(length=10),
                type_=sa.String(length=80),
                existing_nullable=True,
            )


def downgrade():
    columns = _column_names("driver_log")
    with op.batch_alter_table("driver_log", schema=None) as batch_op:
        if "depart_load_size" in columns:
            batch_op.alter_column(
                "depart_load_size",
                existing_type=sa.String(length=80),
                type_=sa.String(length=10),
                existing_nullable=True,
            )
        batch_op.alter_column(
            "load_size",
            existing_type=sa.String(length=80),
            type_=sa.String(length=10),
            existing_nullable=False,
        )
