"""Add duty_status_event table for the Daily Log (OFF/SB/D/ON record of duty
status) in the day-driver workspace.

Revision ID: a7b8c9d0e1f2
Revises: d1e2f3a4b5c6
Create Date: 2026-06-11 00:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "a7b8c9d0e1f2"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def _has_table(name):
    return inspect(op.get_bind()).has_table(name)


def upgrade():
    if not _has_table("duty_status_event"):
        op.create_table(
            "duty_status_event",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False, index=True),
            sa.Column("status", sa.String(length=4), nullable=False),
            sa.Column("at", sa.DateTime(), nullable=False, index=True),
            sa.Column("location", sa.String(length=160), nullable=True),
            sa.Column("note", sa.String(length=200), nullable=True),
            sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )


def downgrade():
    if _has_table("duty_status_event"):
        op.drop_table("duty_status_event")
