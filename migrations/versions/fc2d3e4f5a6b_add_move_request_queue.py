"""Add move request queue

Revision ID: fc2d3e4f5a6b
Revises: fb1c2d3e4f5a
Create Date: 2026-05-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "fc2d3e4f5a6b"
down_revision = "fb1c2d3e4f5a"
branch_labels = None
depends_on = None


def _has_table(table_name):
    return inspect(op.get_bind()).has_table(table_name)


def upgrade():
    if _has_table("move_request"):
        return

    op.create_table(
        "move_request",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_number", sa.String(length=50), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.String(length=120), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("request_type", sa.String(length=30), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("origin_location_text", sa.String(length=160), nullable=True),
        sa.Column("destination_location_text", sa.String(length=160), nullable=True),
        sa.Column("cargo_text", sa.Text(), nullable=True),
        sa.Column("part_number", sa.String(length=80), nullable=True),
        sa.Column("quantity_value", sa.Float(), nullable=True),
        sa.Column("quantity_unit", sa.String(length=40), nullable=True),
        sa.Column("quantity_text", sa.String(length=120), nullable=True),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("due_time_text", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
        sa.Column("closed_reason", sa.Text(), nullable=True),
        sa.Column("assigned_driver_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("assigned_driver_text", sa.String(length=120), nullable=True),
        sa.Column("equipment_id", sa.String(length=80), nullable=True),
        sa.Column("equipment_text", sa.String(length=120), nullable=True),
        sa.Column("linked_driver_log_id", sa.Integer(), sa.ForeignKey("driver_log.id"), nullable=True),
        sa.Column("linked_route_id", sa.String(length=80), nullable=True),
        sa.Column("linked_plant_transfer_id", sa.Integer(), sa.ForeignKey("plant_transfer.id"), nullable=True),
        sa.Column("linked_document_id", sa.Integer(), sa.ForeignKey("external_document.id"), nullable=True),
        sa.Column("parsed_confidence", sa.String(length=30), nullable=True),
        sa.Column("parse_warnings", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("request_number", name="uq_move_request_request_number"),
    )
    op.create_index("ix_move_request_assigned_driver_id", "move_request", ["assigned_driver_id"])
    op.create_index("ix_move_request_due_at", "move_request", ["due_at"])
    op.create_index("ix_move_request_linked_driver_log_id", "move_request", ["linked_driver_log_id"])
    op.create_index("ix_move_request_linked_plant_transfer_id", "move_request", ["linked_plant_transfer_id"])
    op.create_index("ix_move_request_linked_route_id", "move_request", ["linked_route_id"])
    op.create_index("ix_move_request_part_number", "move_request", ["part_number"])
    op.create_index("ix_move_request_priority", "move_request", ["priority"])
    op.create_index("ix_move_request_request_number", "move_request", ["request_number"])
    op.create_index("ix_move_request_request_type", "move_request", ["request_type"])
    op.create_index("ix_move_request_requested_at", "move_request", ["requested_at"])
    op.create_index("ix_move_request_source", "move_request", ["source"])
    op.create_index("ix_move_request_status", "move_request", ["status"])


def downgrade():
    if _has_table("move_request"):
        op.drop_table("move_request")
