"""add taxonomy lifecycle fields to document_content and taxonomy_suggestions table

Adds:
  - document_content.taxonomy_id       (FK → taxonomies, stale detection scope)
  - document_content.classification_method ("llm" | "keyword", for stale detection)
  - document_content.classification_taxonomy_version (already exists in some schemas — guarded)
  - taxonomy_suggestions table (term suggestion capture from enrichment pipeline)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-02 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------
    # document_content: add taxonomy_id (stale detection scope)
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'document_content'
                  AND column_name = 'taxonomy_id'
            ) THEN
                ALTER TABLE document_content
                    ADD COLUMN taxonomy_id VARCHAR(36)
                    REFERENCES taxonomies(id) ON DELETE SET NULL;
            END IF;
        END
        $$;
    """))

    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_document_content_taxonomy_id
            ON document_content (taxonomy_id);
    """))

    # ------------------------------------------------------------------
    # document_content: add classification_method ("llm" | "keyword")
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'document_content'
                  AND column_name = 'classification_method'
            ) THEN
                ALTER TABLE document_content
                    ADD COLUMN classification_method VARCHAR(20);
            END IF;
        END
        $$;
    """))

    # ------------------------------------------------------------------
    # document_content: classification_taxonomy_version (may already exist)
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'document_content'
                  AND column_name = 'classification_taxonomy_version'
            ) THEN
                ALTER TABLE document_content
                    ADD COLUMN classification_taxonomy_version INTEGER;
            END IF;
        END
        $$;
    """))

    # ------------------------------------------------------------------
    # taxonomy_suggestions table
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS taxonomy_suggestions (
            id               VARCHAR(36)  NOT NULL,
            taxonomy_id      VARCHAR(36)  NOT NULL,
            facet            VARCHAR(100) NOT NULL,
            suggested_value  VARCHAR(200) NOT NULL,
            frequency        INTEGER      NOT NULL DEFAULT 1,
            sample_document_ids JSON,
            status           VARCHAR(20)  NOT NULL DEFAULT 'pending',
            merged_into      VARCHAR(200),
            created_at       TIMESTAMP    NOT NULL DEFAULT now(),
            reviewed_at      TIMESTAMP,
            PRIMARY KEY (id),
            FOREIGN KEY (taxonomy_id) REFERENCES taxonomies(id) ON DELETE CASCADE,
            CONSTRAINT uq_taxonomy_suggestion UNIQUE (taxonomy_id, facet, suggested_value)
        );
    """))

    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_taxonomy_suggestions_taxonomy_id
            ON taxonomy_suggestions (taxonomy_id);
    """))


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("DROP TABLE IF EXISTS taxonomy_suggestions;"))

    for col in ["taxonomy_id", "classification_method"]:
        conn.execute(sa.text(f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'document_content'
                      AND column_name = '{col}'
                ) THEN
                    ALTER TABLE document_content DROP COLUMN {col};
                END IF;
            END
            $$;
        """))
