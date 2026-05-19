"""Add driver log stop photo proof

Revision ID: f9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-05-19 18:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "f9b0c1d2e3f4"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def _has_table(table_name):
    return inspect(op.get_bind()).has_table(table_name)


def upgrade():
    if _has_table("driver_log_photo"):
        return
    op.create_table(
        "driver_log_photo",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(length=80), nullable=False, server_default="lacksdrivers"),
        sa.Column("driver_log_id", sa.Integer(), sa.ForeignKey("driver_log.id"), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=False, server_default="gallery"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("uploaded_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_driver_log_photo_driver_log_id", "driver_log_photo", ["driver_log_id"])


def downgrade():
    if _has_table("driver_log_photo"):
        op.drop_index("ix_driver_log_photo_driver_log_id", table_name="driver_log_photo")
        op.drop_table("driver_log_photo")
