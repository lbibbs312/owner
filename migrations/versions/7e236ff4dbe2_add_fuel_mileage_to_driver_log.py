"""add fuel_mileage to driver_log

Revision ID: 7e236ff4dbe2
Revises: f7a8b9c0d1e2
Create Date: 2026-05-15 17:52:29.524725

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7e236ff4dbe2'
down_revision = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('driver_log', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fuel_mileage', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('driver_log', schema=None) as batch_op:
        batch_op.drop_column('fuel_mileage')
