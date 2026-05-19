"""Add parts scanning tables

Revision ID: c6d7e8f9a0b1
Revises: b7c1d2e3f4a5
Create Date: 2026-05-19 08:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "c6d7e8f9a0b1"
down_revision = "b7c1d2e3f4a5"
branch_labels = None
depends_on = None


def _has_table(table_name):
    return inspect(op.get_bind()).has_table(table_name)


def upgrade():
    if not _has_table("part_master"):
        op.create_table(
            "part_master",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=80), nullable=False),
            sa.Column("canonical_part_number", sa.String(length=120), nullable=False),
            sa.Column("description", sa.String(length=255), nullable=True),
            sa.Column("customer", sa.String(length=120), nullable=True),
            sa.Column("program", sa.String(length=120), nullable=True),
            sa.Column("default_origin_plant_id", sa.String(length=50), nullable=True),
            sa.Column("default_destination_plant_id", sa.String(length=50), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.Column("first_seen_at", sa.DateTime(), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(), nullable=False),
            sa.Column("seen_count", sa.Integer(), nullable=False),
        )
        op.create_index("ix_part_master_canonical_part_number", "part_master", ["canonical_part_number"])

    if not _has_table("part_alias"):
        op.create_table(
            "part_alias",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("part_id", sa.Integer(), sa.ForeignKey("part_master.id"), nullable=False),
            sa.Column("raw_barcode_value", sa.String(length=255), nullable=False),
            sa.Column("normalized_value", sa.String(length=120), nullable=False),
            sa.Column("symbology", sa.String(length=80), nullable=True),
            sa.Column("label_source", sa.String(length=80), nullable=True),
            sa.Column("first_seen_at", sa.DateTime(), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_part_alias_normalized_value", "part_alias", ["normalized_value"])

    if not _has_table("part_scan_event"):
        op.create_table(
            "part_scan_event",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=80), nullable=False),
            sa.Column("raw_value", sa.String(length=255), nullable=False),
            sa.Column("normalized_value", sa.String(length=120), nullable=False),
            sa.Column("barcode_format", sa.String(length=80), nullable=True),
            sa.Column("part_id", sa.Integer(), sa.ForeignKey("part_master.id"), nullable=True),
            sa.Column("move_id", sa.Integer(), sa.ForeignKey("task.id"), nullable=True),
            sa.Column("stop_id", sa.Integer(), sa.ForeignKey("driver_log.id"), nullable=True),
            sa.Column("driver_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("truck_id", sa.String(length=50), nullable=True),
            sa.Column("trailer_id", sa.String(length=50), nullable=True),
            sa.Column("plant_id", sa.String(length=50), nullable=True),
            sa.Column("scan_context", sa.String(length=40), nullable=False),
            sa.Column("timestamp", sa.DateTime(), nullable=False),
            sa.Column("device_id", sa.String(length=120), nullable=True),
            sa.Column("gps_lat", sa.Float(), nullable=True),
            sa.Column("gps_lng", sa.Float(), nullable=True),
            sa.Column("validation_status", sa.String(length=40), nullable=False),
            sa.Column("validation_message", sa.String(length=255), nullable=True),
            sa.Column("created_offline", sa.Boolean(), nullable=False),
            sa.Column("synced_at", sa.DateTime(), nullable=True),
            sa.Column("damage_report_id", sa.Integer(), sa.ForeignKey("damage_report.id"), nullable=True),
            sa.Column("delay_log_id", sa.Integer(), sa.ForeignKey("driver_log.id"), nullable=True),
        )
        op.create_index("ix_part_scan_event_normalized_value", "part_scan_event", ["normalized_value"])

    if not _has_table("move_part"):
        op.create_table(
            "move_part",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("move_id", sa.Integer(), sa.ForeignKey("task.id"), nullable=False),
            sa.Column("part_id", sa.Integer(), sa.ForeignKey("part_master.id"), nullable=False),
            sa.Column("expected_quantity", sa.Integer(), nullable=False),
            sa.Column("picked_quantity", sa.Integer(), nullable=False),
            sa.Column("dropped_quantity", sa.Integer(), nullable=False),
            sa.Column("current_status", sa.String(length=40), nullable=False),
            sa.Column("expected_drop_stop_id", sa.Integer(), sa.ForeignKey("driver_log.id"), nullable=True),
            sa.Column("actual_drop_stop_id", sa.Integer(), sa.ForeignKey("driver_log.id"), nullable=True),
        )

    if not _has_table("part_location_history"):
        op.create_table(
            "part_location_history",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("part_id", sa.Integer(), sa.ForeignKey("part_master.id"), nullable=False),
            sa.Column("plant_id", sa.String(length=50), nullable=True),
            sa.Column("stop_id", sa.Integer(), sa.ForeignKey("driver_log.id"), nullable=True),
            sa.Column("move_id", sa.Integer(), sa.ForeignKey("task.id"), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("timestamp", sa.DateTime(), nullable=False),
            sa.Column("source_scan_event_id", sa.Integer(), sa.ForeignKey("part_scan_event.id"), nullable=True),
        )


def downgrade():
    for table_name in ("part_location_history", "move_part", "part_scan_event", "part_alias", "part_master"):
        if _has_table(table_name):
            op.drop_table(table_name)
