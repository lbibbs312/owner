"""Add load intent prediction tables

Revision ID: fa0b1c2d3e4f
Revises: f9b0c1d2e3f4
Create Date: 2026-05-20 16:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "fa0b1c2d3e4f"
down_revision = "f9b0c1d2e3f4"
branch_labels = None
depends_on = None


def _has_table(table_name):
    return inspect(op.get_bind()).has_table(table_name)


def upgrade():
    if not _has_table("load_intent"):
        op.create_table(
            "load_intent",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("route_id", sa.String(length=80), nullable=True),
            sa.Column("stop_id", sa.Integer(), sa.ForeignKey("driver_log.id"), nullable=True),
            sa.Column("driver_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("truck_id", sa.String(length=50), nullable=True),
            sa.Column("pickup_plant_id", sa.String(length=50), nullable=True),
            sa.Column("destination_plant_id", sa.String(length=50), nullable=True),
            sa.Column("load_label", sa.String(length=160), nullable=True),
            sa.Column("source", sa.String(length=40), nullable=False),
            sa.Column("confidence", sa.String(length=30), nullable=False),
            sa.Column("predicted_ready_at", sa.DateTime(), nullable=True),
            sa.Column("estimated_remaining_minutes", sa.Integer(), nullable=True),
            sa.Column("reason_text", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("confirmed_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("confirmed_at", sa.DateTime(), nullable=True),
            sa.Column("promoted_driver_log_id", sa.Integer(), sa.ForeignKey("driver_log.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_load_intent_route_id", "load_intent", ["route_id"])
        op.create_index("ix_load_intent_stop_id", "load_intent", ["stop_id"])
        op.create_index("ix_load_intent_driver_id", "load_intent", ["driver_id"])
        op.create_index("ix_load_intent_truck_id", "load_intent", ["truck_id"])
        op.create_index("ix_load_intent_pickup_plant_id", "load_intent", ["pickup_plant_id"])
        op.create_index("ix_load_intent_destination_plant_id", "load_intent", ["destination_plant_id"])

    if not _has_table("plant_prediction_rule"):
        op.create_table(
            "plant_prediction_rule",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("plant_id", sa.String(length=50), nullable=False),
            sa.Column("condition_json", sa.Text(), nullable=True),
            sa.Column("predicted_destination_plant_id", sa.String(length=50), nullable=False),
            sa.Column("confidence", sa.String(length=30), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_plant_prediction_rule_plant_id", "plant_prediction_rule", ["plant_id"])
        op.create_index("ix_plant_prediction_rule_predicted_destination_plant_id", "plant_prediction_rule", ["predicted_destination_plant_id"])

    if not _has_table("plant_time_sample"):
        op.create_table(
            "plant_time_sample",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("plant_id", sa.String(length=50), nullable=False),
            sa.Column("stop_id", sa.Integer(), sa.ForeignKey("driver_log.id"), nullable=True),
            sa.Column("route_id", sa.String(length=80), nullable=True),
            sa.Column("load_type", sa.String(length=40), nullable=True),
            sa.Column("manifest_line_count", sa.Integer(), nullable=True),
            sa.Column("container_count", sa.Integer(), nullable=True),
            sa.Column("gross_weight", sa.Float(), nullable=True),
            sa.Column("hot_flag", sa.Boolean(), nullable=False),
            sa.Column("arrived_at", sa.DateTime(), nullable=True),
            sa.Column("departed_at", sa.DateTime(), nullable=True),
            sa.Column("elapsed_minutes", sa.Integer(), nullable=True),
            sa.Column("included_in_average", sa.Boolean(), nullable=False),
            sa.Column("excluded_reason", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_plant_time_sample_plant_id", "plant_time_sample", ["plant_id"])
        op.create_index("ix_plant_time_sample_stop_id", "plant_time_sample", ["stop_id"])
        op.create_index("ix_plant_time_sample_route_id", "plant_time_sample", ["route_id"])


def downgrade():
    for table_name in ("plant_time_sample", "plant_prediction_rule", "load_intent"):
        if _has_table(table_name):
            op.drop_table(table_name)
