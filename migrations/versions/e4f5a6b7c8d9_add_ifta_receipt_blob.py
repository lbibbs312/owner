"""Store IFTA receipt bytes in the database

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-06-12 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "e4f5a6b7c8d9"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def _columns(table):
    return {col["name"] for col in inspect(op.get_bind()).get_columns(table)}


def upgrade():
    columns = _columns("ifta_fuel_record")
    if "receipt_data" not in columns:
        op.add_column("ifta_fuel_record", sa.Column("receipt_data", sa.LargeBinary(), nullable=True))
    if "receipt_mimetype" not in columns:
        op.add_column("ifta_fuel_record", sa.Column("receipt_mimetype", sa.String(length=100), nullable=True))


def downgrade():
    columns = _columns("ifta_fuel_record")
    if "receipt_mimetype" in columns:
        op.drop_column("ifta_fuel_record", "receipt_mimetype")
    if "receipt_data" in columns:
        op.drop_column("ifta_fuel_record", "receipt_data")
