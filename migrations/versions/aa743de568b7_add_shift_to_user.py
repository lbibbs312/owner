"""add shift to user

Revision ID: aa743de568b7
Revises: 7e236ff4dbe2
Create Date: 2026-05-15 18:08:07.582633

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'aa743de568b7'
down_revision = '7e236ff4dbe2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('shift', sa.String(length=16), nullable=True))


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('shift')
