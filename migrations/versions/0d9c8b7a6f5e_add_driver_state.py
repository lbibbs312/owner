"""Add driver_state (server-side one-driver app state)

Revision ID: 0d9c8b7a6f5e
Revises: f6a7b8c9d0e1
Create Date: 2026-06-16 00:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0d9c8b7a6f5e"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def _has_table(table_name):
    return table_name in inspect(op.get_bind()).get_table_names()


def upgrade():
    if not _has_table("driver_state"):
        op.create_table(
            "driver_state",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
            sa.Column("data", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("user_id", name="uq_driver_state_user_id"),
        )
        op.create_index("ix_driver_state_user_id", "driver_state", ["user_id"])


def downgrade():
    if _has_table("driver_state"):
        op.drop_index("ix_driver_state_user_id", table_name="driver_state")
        op.drop_table("driver_state")
