"""Add operational tracking tables

Revision ID: d5e6f7a8b9c0
Revises: c4f0e2d1a9b3
Create Date: 2026-05-15 01:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "d5e6f7a8b9c0"
down_revision = "c4f0e2d1a9b3"
branch_labels = None
depends_on = None


def _has_table(table_name):
    return inspect(op.get_bind()).has_table(table_name)


def _column_names(table_name):
    if not _has_table(table_name):
        return set()
    return {column["name"] for column in inspect(op.get_bind()).get_columns(table_name)}


def _add_column_if_missing(table_name, column):
    if column.name not in _column_names(table_name):
        op.add_column(table_name, column)


def upgrade():
    _add_column_if_missing("driver_log", sa.Column("dock_wait_minutes", sa.Integer(), nullable=True))
    _add_column_if_missing("plant_transfer", sa.Column("driver_initials", sa.String(length=12), nullable=True))

    if not _has_table("audit_event"):
        op.create_table(
            "audit_event",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
            sa.Column("target_type", sa.String(length=50), nullable=False),
            sa.Column("target_id", sa.Integer(), nullable=False),
            sa.Column("action", sa.String(length=50), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("before_values", sa.Text(), nullable=True),
            sa.Column("after_values", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    if not _has_table("damage_report"):
        op.create_table(
            "damage_report",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("reported_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
            sa.Column("task_id", sa.Integer(), sa.ForeignKey("task.id"), nullable=True),
            sa.Column("driver_log_id", sa.Integer(), sa.ForeignKey("driver_log.id"), nullable=True),
            sa.Column("plant_transfer_id", sa.Integer(), sa.ForeignKey("plant_transfer.id"), nullable=True),
            sa.Column("truck_number", sa.String(length=50), nullable=True),
            sa.Column("trailer_number", sa.String(length=50), nullable=True),
            sa.Column("plant_name", sa.String(length=50), nullable=False),
            sa.Column("damage_time", sa.DateTime(), nullable=False),
            sa.Column("stage", sa.String(length=20), nullable=False),
            sa.Column("move_reference", sa.String(length=150), nullable=True),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
        )
    if not _has_table("damage_photo"):
        op.create_table(
            "damage_photo",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("damage_report_id", sa.Integer(), sa.ForeignKey("damage_report.id"), nullable=False),
            sa.Column("stage", sa.String(length=20), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("original_filename", sa.String(length=255), nullable=True),
            sa.Column("content_type", sa.String(length=100), nullable=True),
            sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        )
    if not _has_table("operational_follow_up"):
        op.create_table(
            "operational_follow_up",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
            sa.Column("kind", sa.String(length=40), nullable=False),
            sa.Column("plant_name", sa.String(length=50), nullable=True),
            sa.Column("details", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
        )


def downgrade():
    for table_name in ("operational_follow_up", "damage_photo", "damage_report", "audit_event"):
        if _has_table(table_name):
            op.drop_table(table_name)
    if "driver_initials" in _column_names("plant_transfer"):
        op.drop_column("plant_transfer", "driver_initials")
    if "dock_wait_minutes" in _column_names("driver_log"):
        op.drop_column("driver_log", "dock_wait_minutes")
