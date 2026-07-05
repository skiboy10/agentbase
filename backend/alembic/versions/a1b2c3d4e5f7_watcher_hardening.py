"""watcher hardening — status columns + watcher_events table

Revision ID: a1b2c3d4e5f6
Revises: e6f7a8b9c0d1
Create Date: 2026-04-17

"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f7'
down_revision = 'e6f7a8b9c0d1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add runtime status columns to sources
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE sources ADD COLUMN IF NOT EXISTS watch_status VARCHAR(20) NOT NULL DEFAULT 'stopped';
            ALTER TABLE sources ADD COLUMN IF NOT EXISTS watch_last_heartbeat_at TIMESTAMP NULL;
            ALTER TABLE sources ADD COLUMN IF NOT EXISTS watch_last_error TEXT NULL;
        END $$;
    """)

    # Create watcher_events table
    op.create_table(
        'watcher_events',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('source_id', sa.String(36), sa.ForeignKey('sources.id', ondelete='CASCADE'), nullable=False),
        sa.Column('timestamp', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('event_type', sa.String(32), nullable=False),
        sa.Column('file_path', sa.String(1024), nullable=True),
        sa.Column('severity', sa.String(8), nullable=False, server_default='info'),
        sa.Column('message', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_watcher_events_source_id', 'watcher_events', ['source_id'])
    op.create_index('ix_watcher_events_timestamp', 'watcher_events', ['timestamp'])
    op.execute(
        'CREATE INDEX ix_watcher_events_source_timestamp ON watcher_events (source_id, timestamp DESC)'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS ix_watcher_events_source_timestamp')
    op.drop_index('ix_watcher_events_timestamp', table_name='watcher_events')
    op.drop_index('ix_watcher_events_source_id', table_name='watcher_events')
    op.drop_table('watcher_events')

    op.execute("""
        DO $$ BEGIN
            ALTER TABLE sources DROP COLUMN IF EXISTS watch_status;
            ALTER TABLE sources DROP COLUMN IF EXISTS watch_last_heartbeat_at;
            ALTER TABLE sources DROP COLUMN IF EXISTS watch_last_error;
        END $$;
    """)
