"""Add review_status to driver_log_photo

Revision ID: 3d4e5f607182
Revises: 2c3d4e5f6071
Create Date: 2026-06-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "3d4e5f607182"
down_revision = "2c3d4e5f6071"
branch_labels = None
depends_on = None


def _has_column(table_name, column_name):
    return column_name in {column["name"] for column in inspect(op.get_bind()).get_columns(table_name)}


def upgrade():
    if not _has_column("driver_log_photo", "review_status"):
        with op.batch_alter_table("driver_log_photo", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("review_status", sa.String(length=20), nullable=False, server_default="review_optional")
            )


def downgrade():
    if _has_column("driver_log_photo", "review_status"):
        with op.batch_alter_table("driver_log_photo", schema=None) as batch_op:
            batch_op.drop_column("review_status")
