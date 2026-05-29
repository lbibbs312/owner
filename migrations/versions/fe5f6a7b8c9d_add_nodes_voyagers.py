"""Add Node and Voyager first-class entities

Revision ID: fe5f6a7b8c9d
Revises: fd4e5f6a7b8c
Create Date: 2026-05-29 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "fe5f6a7b8c9d"
down_revision = "fd4e5f6a7b8c"
branch_labels = None
depends_on = None


def _has_table(table_name):
    return inspect(op.get_bind()).has_table(table_name)


def upgrade():
    if not _has_table("node"):
        op.create_table(
            "node",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=80), nullable=False),
            sa.Column("key", sa.String(length=120), nullable=False),
            sa.Column("short_code", sa.String(length=40), nullable=True),
            sa.Column("label", sa.String(length=160), nullable=False),
            sa.Column("node_type", sa.String(length=40), nullable=False),
            sa.Column("allowed_equipment_types", sa.JSON(), nullable=False),
            sa.Column("section", sa.String(length=80), nullable=True),
            sa.Column("row", sa.String(length=80), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("tenant_id", "key", name="uq_node_tenant_key"),
        )
        op.create_index("ix_node_tenant_id", "node", ["tenant_id"])
        op.create_index("ix_node_key", "node", ["key"])
        op.create_index("ix_node_short_code", "node", ["short_code"])
        op.create_index("ix_node_node_type", "node", ["node_type"])

    if not _has_table("voyager"):
        op.create_table(
            "voyager",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=80), nullable=False),
            sa.Column("equipment_id", sa.String(length=80), nullable=False),
            sa.Column("equipment_type", sa.String(length=40), nullable=False),
            sa.Column("driver_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("current_node_key", sa.String(length=120), nullable=True),
            sa.Column("current_status", sa.String(length=40), nullable=False),
            sa.Column("current_load_utilization", sa.String(length=20), nullable=False),
            sa.Column("current_manifest_id", sa.Integer(), sa.ForeignKey("flow_manifest.id"), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("tenant_id", "equipment_id", name="uq_voyager_tenant_equipment"),
        )
        op.create_index("ix_voyager_tenant_id", "voyager", ["tenant_id"])
        op.create_index("ix_voyager_equipment_id", "voyager", ["equipment_id"])
        op.create_index("ix_voyager_equipment_type", "voyager", ["equipment_type"])
        op.create_index("ix_voyager_driver_id", "voyager", ["driver_id"])
        op.create_index("ix_voyager_current_node_key", "voyager", ["current_node_key"])
        op.create_index("ix_voyager_current_status", "voyager", ["current_status"])
        op.create_index("ix_voyager_current_manifest_id", "voyager", ["current_manifest_id"])


def downgrade():
    if _has_table("voyager"):
        op.drop_table("voyager")
    if _has_table("node"):
        op.drop_table("node")
