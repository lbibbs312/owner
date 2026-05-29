"""Add flow event ledger and projection tables

Revision ID: fd4e5f6a7b8c
Revises: fc2d3e4f5a6b
Create Date: 2026-05-29 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "fd4e5f6a7b8c"
down_revision = "fc2d3e4f5a6b"
branch_labels = None
depends_on = None


def _has_table(table_name):
    return inspect(op.get_bind()).has_table(table_name)


def upgrade():
    if not _has_table("container_type"):
        op.create_table(
            "container_type",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=80), nullable=False),
            sa.Column("code", sa.String(length=40), nullable=False),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.UniqueConstraint("tenant_id", "code", name="uq_container_type_tenant_code"),
        )
        op.create_index("ix_container_type_tenant_id", "container_type", ["tenant_id"])

    if not _has_table("flow_manifest"):
        op.create_table(
            "flow_manifest",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=80), nullable=False),
            sa.Column("manifest_number", sa.String(length=120), nullable=False),
            sa.Column("shipper_id", sa.String(length=120), nullable=True),
            sa.Column("route_id", sa.String(length=80), nullable=True),
            sa.Column("vehicle_id", sa.String(length=80), nullable=True),
            sa.Column("trailer_id", sa.String(length=80), nullable=True),
            sa.Column("driver_id", sa.Integer(), nullable=True),
            sa.Column("origin_node_id", sa.String(length=80), nullable=True),
            sa.Column("destination_node_id", sa.String(length=80), nullable=True),
            sa.Column("current_status", sa.String(length=60), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["driver_id"], ["user.id"]),
            sa.UniqueConstraint("tenant_id", "manifest_number", name="uq_flow_manifest_number"),
        )
        for column in ("tenant_id", "manifest_number", "shipper_id", "route_id", "vehicle_id", "trailer_id", "driver_id", "origin_node_id", "destination_node_id", "current_status"):
            op.create_index(f"ix_flow_manifest_{column}", "flow_manifest", [column])

    if not _has_table("flow_container"):
        op.create_table(
            "flow_container",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=80), nullable=False),
            sa.Column("container_type_id", sa.Integer(), nullable=False),
            sa.Column("identifier", sa.String(length=120), nullable=False),
            sa.Column("parent_container_id", sa.Integer(), nullable=True),
            sa.Column("current_node_id", sa.String(length=80), nullable=True),
            sa.Column("current_status", sa.String(length=60), nullable=False),
            sa.Column("capacity_units", sa.Float(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["container_type_id"], ["container_type.id"]),
            sa.ForeignKeyConstraint(["parent_container_id"], ["flow_container.id"]),
            sa.UniqueConstraint("tenant_id", "identifier", name="uq_flow_container_identifier"),
        )
        for column in ("tenant_id", "container_type_id", "identifier", "parent_container_id", "current_node_id", "current_status"):
            op.create_index(f"ix_flow_container_{column}", "flow_container", [column])

    if not _has_table("container_item"):
        op.create_table(
            "container_item",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=80), nullable=False),
            sa.Column("container_id", sa.Integer(), nullable=False),
            sa.Column("part_sku", sa.String(length=120), nullable=True),
            sa.Column("serial_number", sa.String(length=120), nullable=True),
            sa.Column("lot_id", sa.String(length=120), nullable=True),
            sa.Column("delivery_order_number", sa.String(length=120), nullable=True),
            sa.Column("quantity", sa.Float(), nullable=False),
            sa.Column("disposition", sa.String(length=60), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["container_id"], ["flow_container.id"]),
        )
        for column in ("tenant_id", "container_id", "part_sku", "serial_number", "lot_id", "delivery_order_number", "disposition"):
            op.create_index(f"ix_container_item_{column}", "container_item", [column])

    if not _has_table("manifest_line"):
        op.create_table(
            "manifest_line",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=80), nullable=False),
            sa.Column("manifest_id", sa.Integer(), nullable=False),
            sa.Column("delivery_order_number", sa.String(length=120), nullable=True),
            sa.Column("part_sku", sa.String(length=120), nullable=True),
            sa.Column("serial_number", sa.String(length=120), nullable=True),
            sa.Column("lot_id", sa.String(length=120), nullable=True),
            sa.Column("container_id", sa.Integer(), nullable=True),
            sa.Column("quantity_expected", sa.Float(), nullable=False),
            sa.Column("quantity_scanned", sa.Float(), nullable=False),
            sa.Column("scan_status", sa.String(length=60), nullable=False),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.ForeignKeyConstraint(["container_id"], ["flow_container.id"]),
            sa.ForeignKeyConstraint(["manifest_id"], ["flow_manifest.id"]),
        )
        for column in ("tenant_id", "manifest_id", "delivery_order_number", "part_sku", "serial_number", "lot_id", "container_id", "scan_status"):
            op.create_index(f"ix_manifest_line_{column}", "manifest_line", [column])

    if not _has_table("flow_event"):
        op.create_table(
            "flow_event",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=80), nullable=False),
            sa.Column("event_type", sa.String(length=60), nullable=False),
            sa.Column("entity_type", sa.String(length=50), nullable=False),
            sa.Column("entity_id", sa.String(length=80), nullable=False),
            sa.Column("route_id", sa.String(length=80), nullable=True),
            sa.Column("stop_id", sa.Integer(), nullable=True),
            sa.Column("manifest_id", sa.Integer(), nullable=True),
            sa.Column("vehicle_id", sa.String(length=80), nullable=True),
            sa.Column("trailer_id", sa.String(length=80), nullable=True),
            sa.Column("container_id", sa.Integer(), nullable=True),
            sa.Column("item_id", sa.Integer(), nullable=True),
            sa.Column("actor_user_id", sa.Integer(), nullable=True),
            sa.Column("actor_role", sa.String(length=40), nullable=True),
            sa.Column("origin_node_id", sa.String(length=80), nullable=True),
            sa.Column("destination_node_id", sa.String(length=80), nullable=True),
            sa.Column("occurred_at", sa.DateTime(), nullable=False),
            sa.Column("device_id", sa.String(length=120), nullable=True),
            sa.Column("offline_event_id", sa.String(length=120), nullable=True),
            sa.Column("correlation_id", sa.String(length=120), nullable=True),
            sa.Column("source", sa.String(length=30), nullable=False),
            sa.Column("payload_json", sa.JSON(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("photo_id", sa.Integer(), nullable=True),
            sa.Column("document_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["actor_user_id"], ["user.id"]),
            sa.ForeignKeyConstraint(["container_id"], ["flow_container.id"]),
            sa.ForeignKeyConstraint(["item_id"], ["container_item.id"]),
            sa.ForeignKeyConstraint(["manifest_id"], ["flow_manifest.id"]),
            sa.ForeignKeyConstraint(["stop_id"], ["driver_log.id"]),
        )
        for column in (
            "tenant_id", "event_type", "entity_type", "entity_id", "route_id", "stop_id", "manifest_id",
            "vehicle_id", "trailer_id", "container_id", "item_id", "actor_user_id", "origin_node_id",
            "destination_node_id", "occurred_at", "device_id", "offline_event_id", "correlation_id", "source",
        ):
            op.create_index(f"ix_flow_event_{column}", "flow_event", [column])
        op.create_index("ix_flow_event_offline_idempotency", "flow_event", ["tenant_id", "device_id", "offline_event_id"])

    if not _has_table("entity_current_state"):
        op.create_table(
            "entity_current_state",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=80), nullable=False),
            sa.Column("entity_type", sa.String(length=50), nullable=False),
            sa.Column("entity_id", sa.String(length=80), nullable=False),
            sa.Column("current_status", sa.String(length=60), nullable=False),
            sa.Column("current_node_id", sa.String(length=80), nullable=True),
            sa.Column("parent_container_id", sa.Integer(), nullable=True),
            sa.Column("active_manifest_id", sa.Integer(), nullable=True),
            sa.Column("active_route_id", sa.String(length=80), nullable=True),
            sa.Column("last_event_id", sa.Integer(), nullable=True),
            sa.Column("last_event_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["active_manifest_id"], ["flow_manifest.id"]),
            sa.ForeignKeyConstraint(["last_event_id"], ["flow_event.id"]),
            sa.ForeignKeyConstraint(["parent_container_id"], ["flow_container.id"]),
            sa.UniqueConstraint("tenant_id", "entity_type", "entity_id", name="uq_entity_current_state_entity"),
        )
        for column in ("tenant_id", "entity_type", "entity_id", "current_status", "current_node_id", "parent_container_id", "active_manifest_id", "active_route_id", "last_event_at"):
            op.create_index(f"ix_entity_current_state_{column}", "entity_current_state", [column])

    if not _has_table("flow_node_snapshot"):
        op.create_table(
            "flow_node_snapshot",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=80), nullable=False),
            sa.Column("node_id", sa.String(length=80), nullable=False),
            sa.Column("snapshot_date", sa.Date(), nullable=False),
            sa.Column("wip_count", sa.Integer(), nullable=False),
            sa.Column("staged_count", sa.Integer(), nullable=False),
            sa.Column("loaded_count", sa.Integer(), nullable=False),
            sa.Column("in_transit_count", sa.Integer(), nullable=False),
            sa.Column("received_count", sa.Integer(), nullable=False),
            sa.Column("blocked_count", sa.Integer(), nullable=False),
            sa.Column("proof_needed_count", sa.Integer(), nullable=False),
            sa.Column("exception_count", sa.Integer(), nullable=False),
            sa.Column("last_event_id", sa.Integer(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["last_event_id"], ["flow_event.id"]),
            sa.UniqueConstraint("tenant_id", "node_id", "snapshot_date", name="uq_flow_node_snapshot_day"),
        )
        for column in ("tenant_id", "node_id", "snapshot_date"):
            op.create_index(f"ix_flow_node_snapshot_{column}", "flow_node_snapshot", [column])

    if not _has_table("container_tree_snapshot"):
        op.create_table(
            "container_tree_snapshot",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=80), nullable=False),
            sa.Column("container_id", sa.Integer(), nullable=False),
            sa.Column("parent_container_id", sa.Integer(), nullable=True),
            sa.Column("root_container_id", sa.Integer(), nullable=False),
            sa.Column("current_node_id", sa.String(length=80), nullable=True),
            sa.Column("current_status", sa.String(length=60), nullable=False),
            sa.Column("current_quantity", sa.Float(), nullable=False),
            sa.Column("active_manifest_id", sa.Integer(), nullable=True),
            sa.Column("last_event_id", sa.Integer(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["active_manifest_id"], ["flow_manifest.id"]),
            sa.ForeignKeyConstraint(["container_id"], ["flow_container.id"]),
            sa.ForeignKeyConstraint(["last_event_id"], ["flow_event.id"]),
            sa.ForeignKeyConstraint(["parent_container_id"], ["flow_container.id"]),
            sa.ForeignKeyConstraint(["root_container_id"], ["flow_container.id"]),
            sa.UniqueConstraint("tenant_id", "container_id", name="uq_container_tree_snapshot_container"),
        )
        for column in ("tenant_id", "container_id", "parent_container_id", "root_container_id", "current_node_id", "current_status", "active_manifest_id"):
            op.create_index(f"ix_container_tree_snapshot_{column}", "container_tree_snapshot", [column])


def downgrade():
    for table_name in (
        "container_tree_snapshot",
        "flow_node_snapshot",
        "entity_current_state",
        "flow_event",
        "manifest_line",
        "container_item",
        "flow_container",
        "flow_manifest",
        "container_type",
    ):
        if _has_table(table_name):
            op.drop_table(table_name)
