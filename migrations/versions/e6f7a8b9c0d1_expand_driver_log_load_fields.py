"""Expand driver log load fields for destination loads

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-05-15 15:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("driver_log", schema=None) as batch_op:
        batch_op.alter_column("load_size", existing_type=sa.String(length=10), type_=sa.String(length=80), existing_nullable=False)
        batch_op.alter_column("depart_load_size", existing_type=sa.String(length=10), type_=sa.String(length=80), existing_nullable=True)


def downgrade():
    with op.batch_alter_table("driver_log", schema=None) as batch_op:
        batch_op.alter_column("depart_load_size", existing_type=sa.String(length=80), type_=sa.String(length=10), existing_nullable=True)
        batch_op.alter_column("load_size", existing_type=sa.String(length=80), type_=sa.String(length=10), existing_nullable=False)
