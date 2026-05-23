"""Add password reset fields

Revision ID: c2d3e4f5a6b7
Revises: fb1c2d3e4f5a
Create Date: 2026-05-23 01:40:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "c2d3e4f5a6b7"
down_revision = "fb1c2d3e4f5a"
branch_labels = None
depends_on = None


def _column_names(table_name):
    return {column["name"] for column in inspect(op.get_bind()).get_columns(table_name)}


def upgrade():
    existing_columns = _column_names("user")
    with op.batch_alter_table("user", schema=None) as batch_op:
        if "reset_password_token" not in existing_columns:
            batch_op.add_column(sa.Column("reset_password_token", sa.String(length=128), nullable=True))
        if "reset_password_expires_at" not in existing_columns:
            batch_op.add_column(sa.Column("reset_password_expires_at", sa.DateTime(), nullable=True))

    indexes = {index["name"] for index in inspect(op.get_bind()).get_indexes("user")}
    if "ix_user_reset_password_token" not in indexes:
        op.create_index("ix_user_reset_password_token", "user", ["reset_password_token"], unique=True)


def downgrade():
    indexes = {index["name"] for index in inspect(op.get_bind()).get_indexes("user")}
    if "ix_user_reset_password_token" in indexes:
        op.drop_index("ix_user_reset_password_token", table_name="user")

    existing_columns = _column_names("user")
    with op.batch_alter_table("user", schema=None) as batch_op:
        if "reset_password_expires_at" in existing_columns:
            batch_op.drop_column("reset_password_expires_at")
        if "reset_password_token" in existing_columns:
            batch_op.drop_column("reset_password_token")
