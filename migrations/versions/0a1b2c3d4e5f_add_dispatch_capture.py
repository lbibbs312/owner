"""Add dispatch capture inbox

Revision ID: 0a1b2c3d4e5f
Revises: fe5f6a7b8c9d
Create Date: 2026-05-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0a1b2c3d4e5f"
down_revision = "fe5f6a7b8c9d"
branch_labels = None
depends_on = None


def _has_table(table_name):
    return inspect(op.get_bind()).has_table(table_name)


def upgrade():
    if _has_table("dispatch_capture"):
        return

    op.create_table(
        "dispatch_capture",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(length=80), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("captured_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.Column("guessed_type", sa.String(length=40), nullable=True),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.String(length=20), nullable=True),
        sa.Column("extracted_from_node", sa.String(length=160), nullable=True),
        sa.Column("extracted_to_node", sa.String(length=160), nullable=True),
        sa.Column("extracted_part_numbers", sa.Text(), nullable=True),
        sa.Column("extracted_trailer_ids", sa.Text(), nullable=True),
        sa.Column("extracted_quantities", sa.Text(), nullable=True),
        sa.Column("extracted_people", sa.Text(), nullable=True),
        sa.Column("missing_fields_json", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("converted_entity_type", sa.String(length=50), nullable=True),
        sa.Column("converted_entity_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_dispatch_capture_captured_at", "dispatch_capture", ["captured_at"])
    op.create_index("ix_dispatch_capture_captured_by", "dispatch_capture", ["captured_by"])
    op.create_index("ix_dispatch_capture_converted_entity_id", "dispatch_capture", ["converted_entity_id"])
    op.create_index("ix_dispatch_capture_guessed_type", "dispatch_capture", ["guessed_type"])
    op.create_index("ix_dispatch_capture_priority", "dispatch_capture", ["priority"])
    op.create_index("ix_dispatch_capture_source", "dispatch_capture", ["source"])
    op.create_index("ix_dispatch_capture_status", "dispatch_capture", ["status"])
    op.create_index("ix_dispatch_capture_tenant_id", "dispatch_capture", ["tenant_id"])


def downgrade():
    if _has_table("dispatch_capture"):
        op.drop_table("dispatch_capture")
