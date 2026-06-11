"""Add AutoLog engine tables (sessions, points, segments, candidate/confirmed
stops, candidate actions, driver/place memory, review queue, sync outbox)

Revision ID: d1e2f3a4b5c6
Revises: c9f5e3a2b1d8
Create Date: 2026-06-10 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "d1e2f3a4b5c6"
down_revision = "c9f5e3a2b1d8"
branch_labels = None
depends_on = None


def _has_table(name):
    return inspect(op.get_bind()).has_table(name)


def upgrade():
    if not _has_table("autolog_place_memory"):
        op.create_table(
            "autolog_place_memory",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False, index=True),
            sa.Column("label", sa.String(length=120), nullable=False),
            sa.Column("center_latitude", sa.Float(), nullable=False),
            sa.Column("center_longitude", sa.Float(), nullable=False),
            sa.Column("radius_m", sa.Float(), nullable=False, server_default="150"),
            sa.Column("place_type", sa.String(length=20), nullable=False, server_default="unknown"),
            sa.Column("usual_load", sa.String(length=120), nullable=True),
            sa.Column("visit_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("last_visited_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )

    if not _has_table("autolog_session"):
        op.create_table(
            "autolog_session",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False, index=True),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("ended_at", sa.DateTime(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("live_state", sa.String(length=20), nullable=False, server_default="READY"),
            sa.Column("current_candidate_stop_id", sa.Integer(), nullable=True),
            sa.Column("last_point_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )

    if not _has_table("autolog_location_point"):
        op.create_table(
            "autolog_location_point",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_id", sa.Integer(), sa.ForeignKey("autolog_session.id"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False, index=True),
            sa.Column("client_id", sa.String(length=80), nullable=True, index=True),
            sa.Column("latitude", sa.Float(), nullable=False),
            sa.Column("longitude", sa.Float(), nullable=False),
            sa.Column("accuracy_m", sa.Float(), nullable=True),
            sa.Column("speed_mps", sa.Float(), nullable=True),
            sa.Column("heading", sa.Float(), nullable=True),
            sa.Column("moving", sa.Boolean(), nullable=True),
            sa.Column("recorded_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("session_id", "client_id", name="uq_autolog_point_session_client"),
        )

    if not _has_table("autolog_motion_segment"):
        op.create_table(
            "autolog_motion_segment",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_id", sa.Integer(), sa.ForeignKey("autolog_session.id"), nullable=False, index=True),
            sa.Column("kind", sa.String(length=12), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("ended_at", sa.DateTime(), nullable=True),
            sa.Column("start_latitude", sa.Float(), nullable=True),
            sa.Column("start_longitude", sa.Float(), nullable=True),
            sa.Column("end_latitude", sa.Float(), nullable=True),
            sa.Column("end_longitude", sa.Float(), nullable=True),
            sa.Column("distance_m", sa.Float(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )

    if not _has_table("autolog_candidate_stop"):
        op.create_table(
            "autolog_candidate_stop",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_id", sa.Integer(), sa.ForeignKey("autolog_session.id"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False, index=True),
            sa.Column("sequence", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("center_latitude", sa.Float(), nullable=False),
            sa.Column("center_longitude", sa.Float(), nullable=False),
            sa.Column("arrived_at", sa.DateTime(), nullable=False),
            sa.Column("departed_at", sa.DateTime(), nullable=True),
            sa.Column("dwell_seconds", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("place_memory_id", sa.Integer(), sa.ForeignKey("autolog_place_memory.id"), nullable=True),
            sa.Column("likely_place_label", sa.String(length=120), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
            sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )

    if not _has_table("autolog_candidate_action"):
        op.create_table(
            "autolog_candidate_action",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("candidate_stop_id", sa.Integer(), sa.ForeignKey("autolog_candidate_stop.id"), nullable=False, index=True),
            sa.Column("session_id", sa.Integer(), sa.ForeignKey("autolog_session.id"), nullable=False, index=True),
            sa.Column("action_type", sa.String(length=20), nullable=False, server_default="unknown"),
            sa.Column("confidence", sa.String(length=10), nullable=False, server_default="low"),
            sa.Column("suggested_label", sa.String(length=120), nullable=True),
            sa.Column("status", sa.String(length=12), nullable=False, server_default="suggested"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )

    if not _has_table("autolog_confirmed_stop"):
        op.create_table(
            "autolog_confirmed_stop",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_id", sa.Integer(), sa.ForeignKey("autolog_session.id"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False, index=True),
            sa.Column("candidate_stop_id", sa.Integer(), sa.ForeignKey("autolog_candidate_stop.id"), nullable=True),
            sa.Column("place_memory_id", sa.Integer(), sa.ForeignKey("autolog_place_memory.id"), nullable=True),
            sa.Column("sequence", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("label", sa.String(length=120), nullable=True),
            sa.Column("action_type", sa.String(length=20), nullable=False, server_default="unknown"),
            sa.Column("cargo_label", sa.String(length=120), nullable=True),
            sa.Column("weight", sa.String(length=40), nullable=True),
            sa.Column("arrived_at", sa.DateTime(), nullable=True),
            sa.Column("departed_at", sa.DateTime(), nullable=True),
            sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        )

    if not _has_table("autolog_driver_memory"):
        op.create_table(
            "autolog_driver_memory",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False, index=True),
            sa.Column("memory_type", sa.String(length=20), nullable=False, server_default="load"),
            sa.Column("value", sa.String(length=120), nullable=False),
            sa.Column("normalized_value", sa.String(length=120), nullable=False),
            sa.Column("use_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("last_used_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("user_id", "memory_type", "normalized_value", name="uq_autolog_driver_memory"),
        )

    if not _has_table("autolog_review_queue"):
        op.create_table(
            "autolog_review_queue",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_id", sa.Integer(), sa.ForeignKey("autolog_session.id"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False, index=True),
            sa.Column("candidate_stop_id", sa.Integer(), sa.ForeignKey("autolog_candidate_stop.id"), nullable=False),
            sa.Column("reason", sa.String(length=120), nullable=True),
            sa.Column("status", sa.String(length=12), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )

    if not _has_table("autolog_sync_outbox"):
        op.create_table(
            "autolog_sync_outbox",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False, index=True),
            sa.Column("session_id", sa.Integer(), sa.ForeignKey("autolog_session.id"), nullable=True),
            sa.Column("client_event_id", sa.String(length=80), nullable=False),
            sa.Column("event_type", sa.String(length=40), nullable=False),
            sa.Column("payload_json", sa.JSON(), nullable=True),
            sa.Column("applied", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("received_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("user_id", "client_event_id", name="uq_autolog_sync_client_event"),
        )


def downgrade():
    for name in (
        "autolog_sync_outbox", "autolog_review_queue", "autolog_driver_memory",
        "autolog_confirmed_stop", "autolog_candidate_action", "autolog_candidate_stop",
        "autolog_motion_segment", "autolog_location_point", "autolog_session",
        "autolog_place_memory",
    ):
        if _has_table(name):
            op.drop_table(name)
