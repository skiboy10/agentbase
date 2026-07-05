"""add enrichment fields to knowledge_sources

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-03-28 00:02:00.000000

Adds three columns to knowledge_sources that control the ingestion
enrichment pipeline (text cleaning + LLM classification):
  - enrichment_enabled (BOOLEAN, default FALSE)
  - enrichment_taxonomy_id (VARCHAR, nullable FK → taxonomies.id)
  - enrichment_model (VARCHAR, nullable — overrides default Ollama model)

All additions are guarded with IF NOT EXISTS so the migration is safe
to run against databases that were partially migrated outside Alembic.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # enrichment_enabled — boolean flag, defaults to FALSE
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'knowledge_sources'
                  AND column_name = 'enrichment_enabled'
            ) THEN
                ALTER TABLE knowledge_sources
                    ADD COLUMN enrichment_enabled BOOLEAN NOT NULL DEFAULT FALSE;
            END IF;
        END
        $$;
    """))

    # enrichment_taxonomy_id — nullable FK to taxonomies
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'knowledge_sources'
                  AND column_name = 'enrichment_taxonomy_id'
            ) THEN
                ALTER TABLE knowledge_sources
                    ADD COLUMN enrichment_taxonomy_id VARCHAR(36)
                    REFERENCES taxonomies(id) ON DELETE SET NULL;
            END IF;
        END
        $$;
    """))

    # Index on enrichment_taxonomy_id for FK lookups
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'knowledge_sources'
                  AND indexname = 'ix_knowledge_sources_enrichment_taxonomy_id'
            ) THEN
                CREATE INDEX ix_knowledge_sources_enrichment_taxonomy_id
                    ON knowledge_sources (enrichment_taxonomy_id);
            END IF;
        END
        $$;
    """))

    # enrichment_model — nullable string, overrides default model
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'knowledge_sources'
                  AND column_name = 'enrichment_model'
            ) THEN
                ALTER TABLE knowledge_sources
                    ADD COLUMN enrichment_model VARCHAR(100);
            END IF;
        END
        $$;
    """))


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("""
        ALTER TABLE knowledge_sources
            DROP COLUMN IF EXISTS enrichment_model,
            DROP COLUMN IF EXISTS enrichment_taxonomy_id,
            DROP COLUMN IF EXISTS enrichment_enabled;
    """))

    conn.execute(sa.text("""
        DROP INDEX IF EXISTS ix_knowledge_sources_enrichment_taxonomy_id;
    """))
