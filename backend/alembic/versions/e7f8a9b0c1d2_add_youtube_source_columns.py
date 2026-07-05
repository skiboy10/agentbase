"""add youtube source columns to sources

Adds youtube_backfill_mode and youtube_recent_count to support the native
youtube source type (#133). source_path holds the channel URL; these two
columns control how much of the back catalogue to ingest, per channel.

Revision ID: e7f8a9b0c1d2
Revises: b3c4d5e6f7a8
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa


revision = 'e7f8a9b0c1d2'
down_revision = 'b3c4d5e6f7a8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE sources ADD COLUMN IF NOT EXISTS youtube_backfill_mode VARCHAR(20) NULL;
            ALTER TABLE sources ADD COLUMN IF NOT EXISTS youtube_recent_count INTEGER NULL;
        END $$;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE sources DROP COLUMN IF EXISTS youtube_recent_count;
            ALTER TABLE sources DROP COLUMN IF EXISTS youtube_backfill_mode;
        END $$;
    """)
