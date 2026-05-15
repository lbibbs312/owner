"""add driver_signature to shift_record

Revision ID: 3adc4fb15abb
Revises: aa743de568b7
Create Date: 2026-05-15 18:21:12.477873

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3adc4fb15abb'
down_revision = 'aa743de568b7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('shift_record', schema=None) as batch_op:
        batch_op.add_column(sa.Column('driver_signature', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('signature_timestamp', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('shift_record', schema=None) as batch_op:
        batch_op.drop_column('signature_timestamp')
        batch_op.drop_column('driver_signature')
