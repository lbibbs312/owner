"""Transfer tracking, audit, damage, follow-up, activity

Revision ID: 9b4af2c1d3e0
Revises: e3ee99d416e9
Create Date: 2026-05-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9b4af2c1d3e0'
down_revision = 'e3ee99d416e9'
branch_labels = None
depends_on = None


def upgrade():
    # New tables --------------------------------------------------------------
    op.create_table(
        'plant_transfer',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('transfer_number', sa.String(length=50), nullable=True),
        sa.Column('transfer_date', sa.Date(), nullable=False),
        sa.Column('ship_to', sa.String(length=50), nullable=True),
        sa.Column('ship_from', sa.String(length=50), nullable=True),
        sa.Column('trailer_number', sa.String(length=50), nullable=True),
        sa.Column('driver_name', sa.String(length=120), nullable=True),
        sa.Column('driver_initials', sa.String(length=10), nullable=True),
        sa.Column('transfer_time', sa.String(length=20), nullable=True),
        sa.Column('loaded_by', sa.String(length=120), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('deleted_by_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.ForeignKeyConstraint(['deleted_by_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'plant_transfer_line',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('plant_transfer_id', sa.Integer(), nullable=False),
        sa.Column('line_number', sa.Integer(), nullable=False),
        sa.Column('side', sa.String(length=10), nullable=False),
        sa.Column('part_number', sa.String(length=80), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=True),
        sa.Column('skids', sa.Integer(), nullable=True),
        sa.Column('remarks', sa.String(length=200), nullable=True),
        sa.Column('is_hot', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(['plant_transfer_id'], ['plant_transfer.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('plant_transfer_line', schema=None) as batch_op:
        batch_op.create_index(
            'ix_plant_transfer_line_plant_transfer_id',
            ['plant_transfer_id'],
            unique=False,
        )

    op.create_table(
        'damage_report',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reported_by_id', sa.Integer(), nullable=False),
        sa.Column('driver_log_id', sa.Integer(), nullable=True),
        sa.Column('pretrip_id', sa.Integer(), nullable=True),
        sa.Column('plant_transfer_id', sa.Integer(), nullable=True),
        sa.Column('truck_number', sa.String(length=50), nullable=True),
        sa.Column('trailer_number', sa.String(length=50), nullable=True),
        sa.Column('plant_name', sa.String(length=50), nullable=True),
        sa.Column('damage_time', sa.String(length=20), nullable=True),
        sa.Column('stage', sa.String(length=20), nullable=True),
        sa.Column('move_reference', sa.String(length=120), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='open'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['reported_by_id'], ['user.id']),
        sa.ForeignKeyConstraint(['driver_log_id'], ['driver_log.id']),
        sa.ForeignKeyConstraint(['pretrip_id'], ['pretrip.id']),
        sa.ForeignKeyConstraint(['plant_transfer_id'], ['plant_transfer.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'damage_photo',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('damage_report_id', sa.Integer(), nullable=False),
        sa.Column('stage', sa.String(length=20), nullable=True),
        sa.Column('filename', sa.String(length=200), nullable=False),
        sa.Column('original_filename', sa.String(length=200), nullable=True),
        sa.Column('content_type', sa.String(length=80), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['damage_report_id'], ['damage_report.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('damage_photo', schema=None) as batch_op:
        batch_op.create_index(
            'ix_damage_photo_damage_report_id',
            ['damage_report_id'],
            unique=False,
        )

    op.create_table(
        'audit_event',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('target_type', sa.String(length=80), nullable=False),
        sa.Column('target_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(length=40), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('before_values', sa.Text(), nullable=True),
        sa.Column('after_values', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('audit_event', schema=None) as batch_op:
        batch_op.create_index('ix_audit_event_target_type', ['target_type'], unique=False)
        batch_op.create_index('ix_audit_event_target_id', ['target_id'], unique=False)
        batch_op.create_index('ix_audit_event_created_at', ['created_at'], unique=False)

    op.create_table(
        'operational_follow_up',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=40), nullable=False),
        sa.Column('plant_name', sa.String(length=50), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='open'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'activity_event',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('category', sa.String(length=40), nullable=True),
        sa.Column('action', sa.String(length=40), nullable=True),
        sa.Column('title', sa.String(length=200), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('target_type', sa.String(length=80), nullable=True),
        sa.Column('target_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('activity_event', schema=None) as batch_op:
        batch_op.create_index('ix_activity_event_category', ['category'], unique=False)
        batch_op.create_index('ix_activity_event_created_at', ['created_at'], unique=False)

    # Additive columns on existing tables -----------------------------------
    with op.batch_alter_table('driver_log', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dock_wait_minutes', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('no_pickup', sa.Boolean(), nullable=True, server_default=sa.false()))
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('deleted_by_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_driver_log_deleted_by_id_user',
            'user', ['deleted_by_id'], ['id'],
        )

    with op.batch_alter_table('pretrip', schema=None) as batch_op:
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('deleted_by_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_pretrip_deleted_by_id_user',
            'user', ['deleted_by_id'], ['id'],
        )

    # Task table may not exist depending on which historic branch was applied.
    # Try to add new columns; fall back to a no-op if the table is missing.
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'task' in insp.get_table_names():
        task_cols = {c['name'] for c in insp.get_columns('task')}
        with op.batch_alter_table('task', schema=None) as batch_op:
            if 'is_hot' not in task_cols:
                batch_op.add_column(sa.Column('is_hot', sa.Boolean(), nullable=True, server_default=sa.false()))
            if 'accepted_at' not in task_cols:
                batch_op.add_column(sa.Column('accepted_at', sa.DateTime(), nullable=True))
            if 'completed_at' not in task_cols:
                batch_op.add_column(sa.Column('completed_at', sa.DateTime(), nullable=True))
    else:
        op.create_table(
            'task',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('title', sa.String(length=150), nullable=False),
            sa.Column('details', sa.Text(), nullable=True),
            sa.Column('is_hot', sa.Boolean(), nullable=True, server_default=sa.false()),
            sa.Column('status', sa.String(length=20), nullable=True, server_default='pending'),
            sa.Column('shift', sa.String(length=10), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('assigned_to', sa.Integer(), nullable=True),
            sa.Column('accepted_at', sa.DateTime(), nullable=True),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['assigned_to'], ['user.id']),
            sa.PrimaryKeyConstraint('id'),
        )


def downgrade():
    # Reverse only the additive pieces; leave new tables in place if rolling
    # back partially has happened, but try to be tidy.
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if 'task' in insp.get_table_names():
        task_cols = {c['name'] for c in insp.get_columns('task')}
        with op.batch_alter_table('task', schema=None) as batch_op:
            if 'completed_at' in task_cols:
                batch_op.drop_column('completed_at')
            if 'accepted_at' in task_cols:
                batch_op.drop_column('accepted_at')
            # is_hot may pre-date this migration; leave it alone here.

    with op.batch_alter_table('pretrip', schema=None) as batch_op:
        try:
            batch_op.drop_constraint('fk_pretrip_deleted_by_id_user', type_='foreignkey')
        except Exception:
            pass
        batch_op.drop_column('deleted_by_id')
        batch_op.drop_column('deleted_at')

    with op.batch_alter_table('driver_log', schema=None) as batch_op:
        try:
            batch_op.drop_constraint('fk_driver_log_deleted_by_id_user', type_='foreignkey')
        except Exception:
            pass
        batch_op.drop_column('deleted_by_id')
        batch_op.drop_column('deleted_at')
        batch_op.drop_column('no_pickup')
        batch_op.drop_column('dock_wait_minutes')

    with op.batch_alter_table('activity_event', schema=None) as batch_op:
        batch_op.drop_index('ix_activity_event_created_at')
        batch_op.drop_index('ix_activity_event_category')
    op.drop_table('activity_event')

    op.drop_table('operational_follow_up')

    with op.batch_alter_table('audit_event', schema=None) as batch_op:
        batch_op.drop_index('ix_audit_event_created_at')
        batch_op.drop_index('ix_audit_event_target_id')
        batch_op.drop_index('ix_audit_event_target_type')
    op.drop_table('audit_event')

    with op.batch_alter_table('damage_photo', schema=None) as batch_op:
        batch_op.drop_index('ix_damage_photo_damage_report_id')
    op.drop_table('damage_photo')

    op.drop_table('damage_report')

    with op.batch_alter_table('plant_transfer_line', schema=None) as batch_op:
        batch_op.drop_index('ix_plant_transfer_line_plant_transfer_id')
    op.drop_table('plant_transfer_line')

    op.drop_table('plant_transfer')
