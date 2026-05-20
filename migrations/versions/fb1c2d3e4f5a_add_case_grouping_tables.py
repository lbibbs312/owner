"""Add case grouping tables

Revision ID: fb1c2d3e4f5a
Revises: fa0b1c2d3e4f
Create Date: 2026-05-20 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "fb1c2d3e4f5a"
down_revision = "fa0b1c2d3e4f"
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
    _add_column_if_missing("part_scan_event", sa.Column("route_id", sa.String(length=80), nullable=True))
    _add_column_if_missing("part_scan_event", sa.Column("driver_log_id", sa.Integer(), sa.ForeignKey("driver_log.id"), nullable=True))

    if not _has_table("exception_events"):
        op.create_table(
            "exception_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_type", sa.String(length=50), nullable=False),
            sa.Column("severity", sa.String(length=20), nullable=False),
            sa.Column("route_id", sa.String(length=80), nullable=True),
            sa.Column("stop_id", sa.Integer(), sa.ForeignKey("driver_log.id"), nullable=True),
            sa.Column("driver_log_id", sa.Integer(), sa.ForeignKey("driver_log.id"), nullable=True),
            sa.Column("driver_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("truck_id", sa.String(length=50), nullable=True),
            sa.Column("plant_name", sa.String(length=50), nullable=True),
            sa.Column("event_date", sa.Date(), nullable=True),
            sa.Column("target_type", sa.String(length=50), nullable=True),
            sa.Column("target_id", sa.Integer(), nullable=True),
            sa.Column("summary", sa.String(length=255), nullable=False),
            sa.Column("details", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    if not _has_table("followup_cases"):
        op.create_table(
            "followup_cases",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("case_type", sa.String(length=50), nullable=False),
            sa.Column("title", sa.String(length=160), nullable=False),
            sa.Column("scope_key", sa.String(length=160), nullable=False),
            sa.Column("plant_name", sa.String(length=50), nullable=True),
            sa.Column("truck_id", sa.String(length=50), nullable=True),
            sa.Column("owner_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
        )

    if not _has_table("case_events"):
        op.create_table(
            "case_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("case_id", sa.Integer(), sa.ForeignKey("followup_cases.id"), nullable=False),
            sa.Column("exception_event_id", sa.Integer(), sa.ForeignKey("exception_events.id"), nullable=True),
            sa.Column("target_type", sa.String(length=50), nullable=True),
            sa.Column("target_id", sa.Integer(), nullable=True),
            sa.Column("summary", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )


def downgrade():
    for table_name in ("case_events", "followup_cases", "exception_events"):
        if _has_table(table_name):
            op.drop_table(table_name)
    if "driver_log_id" in _column_names("part_scan_event"):
        op.drop_column("part_scan_event", "driver_log_id")
    if "route_id" in _column_names("part_scan_event"):
        op.drop_column("part_scan_event", "route_id")
