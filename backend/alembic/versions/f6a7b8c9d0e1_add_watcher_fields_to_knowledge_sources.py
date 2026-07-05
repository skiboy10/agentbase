"""add watcher fields to knowledge sources

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-03-28 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add watcher config fields to knowledge_sources
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE knowledge_sources ADD COLUMN IF NOT EXISTS watch_enabled BOOLEAN DEFAULT FALSE;
            ALTER TABLE knowledge_sources ADD COLUMN IF NOT EXISTS watch_extensions JSON;
            ALTER TABLE knowledge_sources ADD COLUMN IF NOT EXISTS watch_max_file_size_mb INTEGER DEFAULT 50;
            ALTER TABLE knowledge_sources ADD COLUMN IF NOT EXISTS watch_debounce_seconds INTEGER DEFAULT 60;
            ALTER TABLE knowledge_sources ADD COLUMN IF NOT EXISTS watch_depth INTEGER DEFAULT 10;
            ALTER TABLE knowledge_sources ADD COLUMN IF NOT EXISTS watch_mode VARCHAR(20) DEFAULT 'auto';
            ALTER TABLE knowledge_sources ADD COLUMN IF NOT EXISTS watch_poll_interval_seconds INTEGER DEFAULT 300;
        END $$;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE knowledge_sources DROP COLUMN IF EXISTS watch_enabled;
            ALTER TABLE knowledge_sources DROP COLUMN IF EXISTS watch_extensions;
            ALTER TABLE knowledge_sources DROP COLUMN IF EXISTS watch_max_file_size_mb;
            ALTER TABLE knowledge_sources DROP COLUMN IF EXISTS watch_debounce_seconds;
            ALTER TABLE knowledge_sources DROP COLUMN IF EXISTS watch_depth;
            ALTER TABLE knowledge_sources DROP COLUMN IF EXISTS watch_mode;
            ALTER TABLE knowledge_sources DROP COLUMN IF EXISTS watch_poll_interval_seconds;
        END $$;
    """)
