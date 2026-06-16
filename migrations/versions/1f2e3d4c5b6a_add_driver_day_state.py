"""Add driver_day_state for day-scoped one-driver app sync

Revision ID: 1f2e3d4c5b6a
Revises: 0d9c8b7a6f5e
Create Date: 2026-06-16 03:20:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "1f2e3d4c5b6a"
down_revision = "0d9c8b7a6f5e"
branch_labels = None
depends_on = None


def _has_table(table_name):
    return inspect(op.get_bind()).has_table(table_name)


def upgrade():
    if not _has_table("driver_day_state"):
        op.create_table(
            "driver_day_state",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
            sa.Column("day_key", sa.String(length=10), nullable=False),
            sa.Column("data", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("user_id", "day_key", name="uq_driver_day_state_user_day"),
        )
        op.create_index("ix_driver_day_state_user_id", "driver_day_state", ["user_id"])
        op.create_index("ix_driver_day_state_day_key", "driver_day_state", ["day_key"])


def downgrade():
    if _has_table("driver_day_state"):
        op.drop_index("ix_driver_day_state_day_key", table_name="driver_day_state")
        op.drop_index("ix_driver_day_state_user_id", table_name="driver_day_state")
        op.drop_table("driver_day_state")
