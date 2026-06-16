"""Add driver presence telemetry

Revision ID: 3b4c5d6e7f80
Revises: 2a3b4c5d6e7f
Create Date: 2026-06-16 19:35:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "3b4c5d6e7f80"
down_revision = "2a3b4c5d6e7f"
branch_labels = None
depends_on = None


def _has_table(table_name):
    return inspect(op.get_bind()).has_table(table_name)


def upgrade():
    if not _has_table("driver_presence"):
        op.create_table(
            "driver_presence",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("session_id", sa.String(length=80), nullable=True),
            sa.Column("first_seen_at", sa.DateTime(), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(), nullable=True),
            sa.Column("last_heartbeat_at", sa.DateTime(), nullable=True),
            sa.Column("active_day_key", sa.String(length=10), nullable=True),
            sa.Column("active_today_seconds", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_active_seconds", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("screen", sa.String(length=32), nullable=True),
            sa.Column("route_state", sa.String(length=32), nullable=True),
            sa.Column("location_label", sa.String(length=160), nullable=True),
            sa.Column("city", sa.String(length=80), nullable=True),
            sa.Column("state", sa.String(length=40), nullable=True),
            sa.Column("current_target", sa.String(length=160), nullable=True),
            sa.Column("stop_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("export_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_export_at", sa.DateTime(), nullable=True),
            sa.Column("last_export_type", sa.String(length=40), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id"),
        )
        op.create_index("ix_driver_presence_user_id", "driver_presence", ["user_id"])
        op.create_index("ix_driver_presence_last_seen_at", "driver_presence", ["last_seen_at"])
        op.create_index("ix_driver_presence_active_day_key", "driver_presence", ["active_day_key"])

    if not _has_table("driver_activity_event"):
        op.create_table(
            "driver_activity_event",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.String(length=32), nullable=False),
            sa.Column("event_label", sa.String(length=128), nullable=True),
            sa.Column("session_id", sa.String(length=80), nullable=True),
            sa.Column("screen", sa.String(length=32), nullable=True),
            sa.Column("location_label", sa.String(length=160), nullable=True),
            sa.Column("city", sa.String(length=80), nullable=True),
            sa.Column("state", sa.String(length=40), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_driver_activity_event_user_id", "driver_activity_event", ["user_id"])
        op.create_index("ix_driver_activity_event_event_type", "driver_activity_event", ["event_type"])
        op.create_index("ix_driver_activity_event_created_at", "driver_activity_event", ["created_at"])


def downgrade():
    if _has_table("driver_activity_event"):
        op.drop_index("ix_driver_activity_event_created_at", table_name="driver_activity_event")
        op.drop_index("ix_driver_activity_event_event_type", table_name="driver_activity_event")
        op.drop_index("ix_driver_activity_event_user_id", table_name="driver_activity_event")
        op.drop_table("driver_activity_event")
    if _has_table("driver_presence"):
        op.drop_index("ix_driver_presence_active_day_key", table_name="driver_presence")
        op.drop_index("ix_driver_presence_last_seen_at", table_name="driver_presence")
        op.drop_index("ix_driver_presence_user_id", table_name="driver_presence")
        op.drop_table("driver_presence")
