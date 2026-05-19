"""Add hot part proof tables

Revision ID: e7f8a9b0c1d2
Revises: c6d7e8f9a0b1
Create Date: 2026-05-19 11:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "e7f8a9b0c1d2"
down_revision = "c6d7e8f9a0b1"
branch_labels = None
depends_on = None


def _inspector():
    return inspect(op.get_bind())


def _has_table(table_name):
    return _inspector().has_table(table_name)


def _columns(table_name):
    if not _has_table(table_name):
        return set()
    return {column["name"] for column in _inspector().get_columns(table_name)}


def _add_part_alias_columns():
    columns = _columns("part_alias")
    if not columns:
        return
    with op.batch_alter_table("part_alias") as batch_op:
        if "tenant_id" not in columns:
            batch_op.add_column(sa.Column("tenant_id", sa.String(length=80), nullable=False, server_default="lacksdrivers"))
        if "raw_scan_value" not in columns:
            batch_op.add_column(sa.Column("raw_scan_value", sa.String(length=255), nullable=False, server_default=""))
        if "label_format" not in columns:
            batch_op.add_column(sa.Column("label_format", sa.String(length=80), nullable=True))


def upgrade():
    _add_part_alias_columns()

    if not _has_table("hot_part_alert"):
        op.create_table(
            "hot_part_alert",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=80), nullable=False),
            sa.Column("part_id", sa.Integer(), sa.ForeignKey("part_master.id"), nullable=True),
            sa.Column("raw_part_number", sa.String(length=120), nullable=True),
            sa.Column("priority", sa.String(length=30), nullable=False),
            sa.Column("source", sa.String(length=30), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("cleared_at", sa.DateTime(), nullable=True),
        )

    if not _has_table("hot_move"):
        op.create_table(
            "hot_move",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=80), nullable=False),
            sa.Column("hot_part_alert_id", sa.Integer(), sa.ForeignKey("hot_part_alert.id"), nullable=True),
            sa.Column("move_id", sa.Integer(), sa.ForeignKey("task.id"), nullable=True),
            sa.Column("driver_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("truck_id", sa.String(length=50), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("accepted_at", sa.DateTime(), nullable=True),
            sa.Column("picked_up_at", sa.DateTime(), nullable=True),
            sa.Column("dropped_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_hot_move_move_id", "hot_move", ["move_id"])

    if not _has_table("hot_part_photo"):
        op.create_table(
            "hot_part_photo",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=80), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("original_filename", sa.String(length=255), nullable=True),
            sa.Column("content_type", sa.String(length=100), nullable=True),
            sa.Column("uploaded_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        )

    if not _has_table("hot_part_event"):
        op.create_table(
            "hot_part_event",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=80), nullable=False),
            sa.Column("hot_move_id", sa.Integer(), sa.ForeignKey("hot_move.id"), nullable=False),
            sa.Column("part_id", sa.Integer(), sa.ForeignKey("part_master.id"), nullable=True),
            sa.Column("event_type", sa.String(length=40), nullable=False),
            sa.Column("raw_scan_value", sa.String(length=255), nullable=True),
            sa.Column("normalized_scan_value", sa.String(length=120), nullable=True),
            sa.Column("photo_id", sa.Integer(), sa.ForeignKey("hot_part_photo.id"), nullable=True),
            sa.Column("driver_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("truck_id", sa.String(length=50), nullable=True),
            sa.Column("stop_id", sa.Integer(), sa.ForeignKey("driver_log.id"), nullable=True),
            sa.Column("plant_id", sa.String(length=50), nullable=True),
            sa.Column("timestamp", sa.DateTime(), nullable=False),
            sa.Column("created_offline", sa.Boolean(), nullable=False),
            sa.Column("synced_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_hot_part_event_hot_move_id", "hot_part_event", ["hot_move_id"])
        op.create_index("ix_hot_part_event_stop_id", "hot_part_event", ["stop_id"])

    if not _has_table("part_route_profile"):
        op.create_table(
            "part_route_profile",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=80), nullable=False),
            sa.Column("part_id", sa.Integer(), sa.ForeignKey("part_master.id"), nullable=False),
            sa.Column("origin_plant_id", sa.String(length=50), nullable=True),
            sa.Column("destination_plant_id", sa.String(length=50), nullable=True),
            sa.Column("route_label", sa.String(length=120), nullable=True),
            sa.Column("times_completed", sa.Integer(), nullable=False),
            sa.Column("times_exception", sa.Integer(), nullable=False),
            sa.Column("confidence_score", sa.Float(), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_part_route_profile_part_id", "part_route_profile", ["part_id"])

    if not _has_table("external_document"):
        op.create_table(
            "external_document",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=80), nullable=False),
            sa.Column("move_id", sa.Integer(), sa.ForeignKey("task.id"), nullable=True),
            sa.Column("document_type", sa.String(length=30), nullable=False),
            sa.Column("file_id", sa.String(length=255), nullable=False),
            sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("uploaded_at", sa.DateTime(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
        )


def downgrade():
    for table_name in (
        "external_document",
        "part_route_profile",
        "hot_part_event",
        "hot_part_photo",
        "hot_move",
        "hot_part_alert",
    ):
        if _has_table(table_name):
            op.drop_table(table_name)

    columns = _columns("part_alias")
    if columns:
        with op.batch_alter_table("part_alias") as batch_op:
            for column_name in ("label_format", "raw_scan_value", "tenant_id"):
                if column_name in columns:
                    batch_op.drop_column(column_name)
