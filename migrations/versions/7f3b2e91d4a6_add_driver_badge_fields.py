"""Add driver badge fields

Revision ID: 7f3b2e91d4a6
Revises: e3ee99d416e9
Create Date: 2026-05-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7f3b2e91d4a6"
down_revision = "e3ee99d416e9"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("first_name", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("last_name", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("employee_id", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("department", sa.String(length=32), nullable=True))


def downgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("department")
        batch_op.drop_column("employee_id")
        batch_op.drop_column("last_name")
        batch_op.drop_column("first_name")
