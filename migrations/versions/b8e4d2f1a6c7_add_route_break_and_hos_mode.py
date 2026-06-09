"""Add route_break table and shift_record.hos_mode for the Hours Check layer

Revision ID: b8e4d2f1a6c7
Revises: a7d3c1e9f042
Create Date: 2026-06-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "b8e4d2f1a6c7"
down_revision = "a7d3c1e9f042"
branch_labels = None
depends_on = None


def _inspector():
    return inspect(op.get_bind())


def _column_names(table_name):
    return {column["name"] for column in _inspector().get_columns(table_name)}


def upgrade():
    tables = set(_inspector().get_table_names())
    if "route_break" not in tables:
        op.create_table(
            "route_break",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("break_date", sa.Date(), nullable=True),
            sa.Column("break_type", sa.String(length=40), nullable=True),
            sa.Column("start_time", sa.DateTime(), nullable=False),
            sa.Column("end_time", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    shift_columns = _column_names("shift_record")
    with op.batch_alter_table("shift_record", schema=None) as batch_op:
        if "hos_mode" not in shift_columns:
            batch_op.add_column(sa.Column("hos_mode", sa.String(length=20), nullable=True))


def downgrade():
    shift_columns = _column_names("shift_record")
    with op.batch_alter_table("shift_record", schema=None) as batch_op:
        if "hos_mode" in shift_columns:
            batch_op.drop_column("hos_mode")

    tables = set(_inspector().get_table_names())
    if "route_break" in tables:
        op.drop_table("route_break")
