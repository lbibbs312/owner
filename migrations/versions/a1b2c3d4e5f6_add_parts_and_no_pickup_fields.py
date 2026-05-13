"""Add task/log parts and no-pickup fields

Revision ID: a1b2c3d4e5f6
Revises: 9d2e4f6a8b10
Create Date: 2026-05-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f6"
down_revision = "9d2e4f6a8b10"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("task", schema=None) as batch_op:
        batch_op.add_column(sa.Column("part_number", sa.String(length=80), nullable=True))

    with op.batch_alter_table("driver_log", schema=None) as batch_op:
        batch_op.add_column(sa.Column("part_number", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("hot_parts", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("no_pickup", sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table("driver_log", schema=None) as batch_op:
        batch_op.drop_column("no_pickup")
        batch_op.drop_column("hot_parts")
        batch_op.drop_column("part_number")

    with op.batch_alter_table("task", schema=None) as batch_op:
        batch_op.drop_column("part_number")
