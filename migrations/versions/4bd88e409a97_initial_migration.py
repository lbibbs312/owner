"""Initial migration

Revision ID: 4bd88e409a97
Revises: 
Create Date: 2025-01-07 03:08:46.438494

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4bd88e409a97'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('user',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=64), nullable=False),
    sa.Column('email', sa.String(length=120), nullable=False),
    sa.Column('password_hash', sa.String(length=128), nullable=True),
    sa.Column('role', sa.String(length=20), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email'),
    sa.UniqueConstraint('username')
    )
    op.create_table('announcement',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=100), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('chat_message',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('room', sa.String(length=100), nullable=True),
    sa.Column('timestamp', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('direct_message',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('sender_id', sa.Integer(), nullable=False),
    sa.Column('receiver_id', sa.Integer(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('timestamp', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['receiver_id'], ['user.id'], ),
    sa.ForeignKeyConstraint(['sender_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('driver_log',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('driver_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=True),
    sa.Column('arrive_time', sa.DateTime(), nullable=True),
    sa.Column('depart_time', sa.DateTime(), nullable=True),
    sa.Column('downtime_reason', sa.String(length=200), nullable=True),
    sa.Column('load_size', sa.String(length=10), nullable=False),
    sa.Column('plant_name', sa.String(length=20), nullable=False),
    sa.Column('maintenance', sa.Boolean(), nullable=True),
    sa.Column('fuel', sa.Boolean(), nullable=True),
    sa.Column('meeting', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['driver_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('pretrip',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('pretrip_date', sa.Date(), nullable=True),
    sa.Column('shift', sa.String(length=10), nullable=True),
    sa.Column('truck_type', sa.String(length=20), nullable=True),
    sa.Column('truck_name', sa.String(length=50), nullable=True),
    sa.Column('start_mileage', sa.Integer(), nullable=True),
    sa.Column('cab_doors_windows', sa.Boolean(), nullable=True),
    sa.Column('body_doors', sa.Boolean(), nullable=True),
    sa.Column('oil_leak', sa.Boolean(), nullable=True),
    sa.Column('grease_leak', sa.Boolean(), nullable=True),
    sa.Column('coolant_leak', sa.Boolean(), nullable=True),
    sa.Column('fuel_leak', sa.Boolean(), nullable=True),
    sa.Column('lights_working', sa.Boolean(), nullable=True),
    sa.Column('tires_ok', sa.Boolean(), nullable=True),
    sa.Column('damage_report', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('task',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=150), nullable=False),
    sa.Column('details', sa.Text(), nullable=True),
    sa.Column('is_hot', sa.Boolean(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('shift', sa.String(length=10), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('assigned_to', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['assigned_to'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('posttrip',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('pretrip_id', sa.Integer(), nullable=False),
    sa.Column('end_mileage', sa.Integer(), nullable=True),
    sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('miles_driven', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['pretrip_id'], ['pretrip.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('posttrip')
    op.drop_table('task')
    op.drop_table('pretrip')
    op.drop_table('driver_log')
    op.drop_table('direct_message')
    op.drop_table('chat_message')
    op.drop_table('announcement')
    op.drop_table('user')
    # ### end Alembic commands ###
