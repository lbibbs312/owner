"""empty message

Revision ID: cd22d3e38ef2
Revises: 28e6b11cd061
Create Date: 2025-01-10 21:05:21.814449

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cd22d3e38ef2'
down_revision = '28e6b11cd061'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('driver_log', schema=None) as batch_op:
        batch_op.alter_column('date',
               existing_type=sa.DATE(),
               nullable=False)

    with op.batch_alter_table('pretrip', schema=None) as batch_op:
        batch_op.add_column(sa.Column('gc_no_defects', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('gauges_ok', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('wipers_ok', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('horn_ok', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('heater_defrost_ok', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('mirrors_ok', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('seat_belts_ok', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('in_cab_no_defects', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('radiator_ok', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('belts_ok', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('hoses_ok', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('air_filter_ok', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('fuel_system_ok', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('ec_no_defects', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('reflectors_ok', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('suspension_ok', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('brakes_ok', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('battery_ok', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('exhaust_ok', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('air_lines_ok', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('light_line_ok', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('fifth_wheel_ok', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('coupling_ok', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('tie_downs_ok', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('rear_end_protection_ok', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('exterior_no_defects', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('towed_bodydoors', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('towed_tiedowns', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('towed_lights', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('towed_reflectors', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('towed_suspension', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('towed_tires', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('towed_wheels', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('towed_brakes', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('towed_landing_gear', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('towed_kingpin', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('towed_fifthwheel', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('towed_othercoupling', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('towed_rearend', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('towed_no_defects', sa.Boolean(), nullable=True))
        batch_op.drop_column('tires_ok')

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('pretrip', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tires_ok', sa.BOOLEAN(), nullable=True))
        batch_op.drop_column('towed_no_defects')
        batch_op.drop_column('towed_rearend')
        batch_op.drop_column('towed_othercoupling')
        batch_op.drop_column('towed_fifthwheel')
        batch_op.drop_column('towed_kingpin')
        batch_op.drop_column('towed_landing_gear')
        batch_op.drop_column('towed_brakes')
        batch_op.drop_column('towed_wheels')
        batch_op.drop_column('towed_tires')
        batch_op.drop_column('towed_suspension')
        batch_op.drop_column('towed_reflectors')
        batch_op.drop_column('towed_lights')
        batch_op.drop_column('towed_tiedowns')
        batch_op.drop_column('towed_bodydoors')
        batch_op.drop_column('exterior_no_defects')
        batch_op.drop_column('rear_end_protection_ok')
        batch_op.drop_column('tie_downs_ok')
        batch_op.drop_column('coupling_ok')
        batch_op.drop_column('fifth_wheel_ok')
        batch_op.drop_column('light_line_ok')
        batch_op.drop_column('air_lines_ok')
        batch_op.drop_column('exhaust_ok')
        batch_op.drop_column('battery_ok')
        batch_op.drop_column('brakes_ok')
        batch_op.drop_column('suspension_ok')
        batch_op.drop_column('reflectors_ok')
        batch_op.drop_column('ec_no_defects')
        batch_op.drop_column('fuel_system_ok')
        batch_op.drop_column('air_filter_ok')
        batch_op.drop_column('hoses_ok')
        batch_op.drop_column('belts_ok')
        batch_op.drop_column('radiator_ok')
        batch_op.drop_column('in_cab_no_defects')
        batch_op.drop_column('seat_belts_ok')
        batch_op.drop_column('mirrors_ok')
        batch_op.drop_column('heater_defrost_ok')
        batch_op.drop_column('horn_ok')
        batch_op.drop_column('wipers_ok')
        batch_op.drop_column('gauges_ok')
        batch_op.drop_column('gc_no_defects')

    with op.batch_alter_table('driver_log', schema=None) as batch_op:
        batch_op.alter_column('date',
               existing_type=sa.DATE(),
               nullable=True)

    # ### end Alembic commands ###
