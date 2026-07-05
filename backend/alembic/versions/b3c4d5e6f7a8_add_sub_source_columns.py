"""add sub-source columns to sources

Adds parent_source_id, path_prefix, path_excludes to support the root /
sub-source model. Sub-sources are filtered views over a root source: same
Qdrant chunks, narrowed by a folder_ancestors filter at query time.

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f7
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa


revision = 'b3c4d5e6f7a8'
down_revision = 'a1b2c3d4e5f7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE sources ADD COLUMN IF NOT EXISTS parent_source_id VARCHAR(36) NULL
                REFERENCES sources(id) ON DELETE CASCADE;
            ALTER TABLE sources ADD COLUMN IF NOT EXISTS path_prefix TEXT NULL;
            ALTER TABLE sources ADD COLUMN IF NOT EXISTS path_excludes JSON NULL;
        END $$;
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sources_parent_source_id ON sources(parent_source_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_sources_parent_source_id")
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE sources DROP COLUMN IF EXISTS path_excludes;
            ALTER TABLE sources DROP COLUMN IF EXISTS path_prefix;
            ALTER TABLE sources DROP COLUMN IF EXISTS parent_source_id;
        END $$;
    """)
