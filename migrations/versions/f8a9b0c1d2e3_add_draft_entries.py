"""add draft entries

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-05-19 13:05:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "f8a9b0c1d2e3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "draft_entry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("draft_key", sa.String(length=255), nullable=False),
        sa.Column("form_id", sa.String(length=120), nullable=True),
        sa.Column("path", sa.String(length=500), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "draft_key", name="uq_draft_entry_user_key"),
    )
    op.create_index("ix_draft_entry_user_updated", "draft_entry", ["user_id", "updated_at"], unique=False)


def downgrade():
    op.drop_index("ix_draft_entry_user_updated", table_name="draft_entry")
    op.drop_table("draft_entry")
