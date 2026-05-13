"""Add task acceptance audit fields

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("task", schema=None) as batch_op:
        batch_op.add_column(sa.Column("accepted_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("accepted_by_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_task_accepted_by_id_user",
            "user",
            ["accepted_by_id"],
            ["id"],
        )


def downgrade():
    with op.batch_alter_table("task", schema=None) as batch_op:
        batch_op.drop_constraint("fk_task_accepted_by_id_user", type_="foreignkey")
        batch_op.drop_column("accepted_by_id")
        batch_op.drop_column("accepted_at")
