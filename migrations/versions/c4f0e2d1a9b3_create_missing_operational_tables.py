"""Create missing operational tables

Revision ID: c4f0e2d1a9b3
Revises: b2c3d4e5f6a7
Create Date: 2026-05-14 21:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "c4f0e2d1a9b3"
down_revision = "b2c3d4e5f6a7"
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
    if not _has_table("activity_event"):
        op.create_table(
            "activity_event",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("category", sa.String(length=30), nullable=False),
            sa.Column("action", sa.String(length=50), nullable=False),
            sa.Column("title", sa.String(length=150), nullable=False),
            sa.Column("details", sa.Text(), nullable=True),
            sa.Column("target_type", sa.String(length=50), nullable=True),
            sa.Column("target_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _has_table("plant_transfer"):
        op.create_table(
            "plant_transfer",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("transfer_number", sa.String(length=30), nullable=True),
            sa.Column("transfer_date", sa.Date(), nullable=False),
            sa.Column("ship_to", sa.String(length=50), nullable=False),
            sa.Column("ship_from", sa.String(length=50), nullable=False),
            sa.Column("trailer_number", sa.String(length=50), nullable=True),
            sa.Column("driver_name", sa.String(length=100), nullable=True),
            sa.Column("transfer_time", sa.String(length=20), nullable=True),
            sa.Column("loaded_by", sa.String(length=100), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            sa.Column("deleted_by_id", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["deleted_by_id"], ["user.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    else:
        _add_column_if_missing(
            "plant_transfer", sa.Column("deleted_at", sa.DateTime(), nullable=True)
        )
        _add_column_if_missing(
            "plant_transfer", sa.Column("deleted_by_id", sa.Integer(), nullable=True)
        )

    if not _has_table("plant_transfer_line"):
        op.create_table(
            "plant_transfer_line",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("plant_transfer_id", sa.Integer(), nullable=False),
            sa.Column("line_number", sa.Integer(), nullable=False),
            sa.Column("side", sa.String(length=5), nullable=False),
            sa.Column("part_number", sa.String(length=80), nullable=True),
            sa.Column("quantity", sa.String(length=30), nullable=True),
            sa.Column("skids", sa.String(length=30), nullable=True),
            sa.Column("remarks", sa.String(length=200), nullable=True),
            sa.ForeignKeyConstraint(["plant_transfer_id"], ["plant_transfer.id"]),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade():
    if _has_table("plant_transfer_line"):
        op.drop_table("plant_transfer_line")
    if _has_table("plant_transfer"):
        op.drop_table("plant_transfer")
    if _has_table("activity_event"):
        op.drop_table("activity_event")
