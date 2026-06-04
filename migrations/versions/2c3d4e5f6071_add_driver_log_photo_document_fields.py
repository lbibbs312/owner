"""Add document_type / owner_type / owner_id to driver_log_photo

Revision ID: 2c3d4e5f6071
Revises: 1b2c3d4e5f60
Create Date: 2026-06-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "2c3d4e5f6071"
down_revision = "1b2c3d4e5f60"
branch_labels = None
depends_on = None


def _has_column(table_name, column_name):
    return column_name in {column["name"] for column in inspect(op.get_bind()).get_columns(table_name)}


def upgrade():
    with op.batch_alter_table("driver_log_photo", schema=None) as batch_op:
        if not _has_column("driver_log_photo", "document_type"):
            batch_op.add_column(sa.Column("document_type", sa.String(length=40), nullable=True))
        if not _has_column("driver_log_photo", "owner_type"):
            batch_op.add_column(sa.Column("owner_type", sa.String(length=30), nullable=True))
        if not _has_column("driver_log_photo", "owner_id"):
            batch_op.add_column(sa.Column("owner_id", sa.String(length=40), nullable=True))


def downgrade():
    with op.batch_alter_table("driver_log_photo", schema=None) as batch_op:
        if _has_column("driver_log_photo", "owner_id"):
            batch_op.drop_column("owner_id")
        if _has_column("driver_log_photo", "owner_type"):
            batch_op.drop_column("owner_type")
        if _has_column("driver_log_photo", "document_type"):
            batch_op.drop_column("document_type")
