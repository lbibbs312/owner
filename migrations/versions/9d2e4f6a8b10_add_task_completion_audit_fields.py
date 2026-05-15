"""Add task completion audit fields

Revision ID: 9d2e4f6a8b10
Revises: 8c1f2a3b4d5e
Create Date: 2026-05-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "9d2e4f6a8b10"
down_revision = "8c1f2a3b4d5e"
branch_labels = None
depends_on = None


def _column_names(table_name):
    return {column["name"] for column in inspect(op.get_bind()).get_columns(table_name)}


def upgrade():
    existing_columns = _column_names("task")
    with op.batch_alter_table("task", schema=None) as batch_op:
        if "completed_at" not in existing_columns:
            batch_op.add_column(sa.Column("completed_at", sa.DateTime(), nullable=True))
        if "completed_by_id" not in existing_columns:
            batch_op.add_column(sa.Column("completed_by_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                "fk_task_completed_by_id_user",
                "user",
                ["completed_by_id"],
                ["id"],
            )


def downgrade():
    with op.batch_alter_table("task", schema=None) as batch_op:
        batch_op.drop_constraint("fk_task_completed_by_id_user", type_="foreignkey")
        batch_op.drop_column("completed_by_id")
        batch_op.drop_column("completed_at")
