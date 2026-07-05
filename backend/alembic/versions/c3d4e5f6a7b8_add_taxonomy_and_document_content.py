"""add taxonomy tables and rename scraped_content to document_content

Revision ID: c3d4e5f6a7b8
Revises: b1a3e7f94c20
Create Date: 2026-03-28 00:00:00.000000

Uses raw SQL with IF NOT EXISTS / DO $$ guards so this migration is safe to
run against databases that were partially set up outside of Alembic.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b1a3e7f94c20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------
    # Part 1: scraped_contents → document_content
    # ------------------------------------------------------------------

    # Rename table only if it still has the old name
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'scraped_contents'
            ) THEN
                ALTER TABLE scraped_contents RENAME TO document_content;
            END IF;
        END
        $$;
    """))

    # Rename the old unique constraint if it exists under the old name
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'uq_scraped_content_source_url'
                  AND table_name = 'document_content'
            ) THEN
                ALTER TABLE document_content
                    RENAME CONSTRAINT uq_scraped_content_source_url
                    TO uq_document_content_source_url;
            END IF;
        END
        $$;
    """))

    # Add new columns to document_content (each guarded with IF NOT EXISTS)
    for col_def in [
        "file_path  VARCHAR(1000)",
        "file_type  VARCHAR(20)",
        "document_type VARCHAR(50)",
        "classification JSON",
    ]:
        col_name = col_def.split()[0]
        conn.execute(sa.text(f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'document_content'
                      AND column_name = '{col_name}'
                ) THEN
                    ALTER TABLE document_content ADD COLUMN {col_def};
                END IF;
            END
            $$;
        """))

    # ------------------------------------------------------------------
    # Part 2: taxonomies table
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS taxonomies (
            id          VARCHAR(36)  NOT NULL,
            name        VARCHAR(255) NOT NULL,
            description TEXT,
            project_id  VARCHAR(36),
            version     INTEGER      NOT NULL DEFAULT 1,
            created_at  TIMESTAMP    NOT NULL DEFAULT now(),
            updated_at  TIMESTAMP    NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
        );
    """))
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_taxonomies_project_id
            ON taxonomies (project_id);
    """))

    # ------------------------------------------------------------------
    # Part 3: taxonomy_terms table
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS taxonomy_terms (
            id           VARCHAR(36)  NOT NULL,
            taxonomy_id  VARCHAR(36)  NOT NULL,
            facet        VARCHAR(100) NOT NULL,
            value        VARCHAR(255) NOT NULL,
            parent_value VARCHAR(255),
            keywords     JSON,
            sort_order   INTEGER      NOT NULL DEFAULT 0,
            created_at   TIMESTAMP    NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            FOREIGN KEY (taxonomy_id) REFERENCES taxonomies (id) ON DELETE CASCADE,
            CONSTRAINT uq_taxonomy_term_facet_value UNIQUE (taxonomy_id, facet, value)
        );
    """))
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_taxonomy_terms_taxonomy_id
            ON taxonomy_terms (taxonomy_id);
    """))


def downgrade() -> None:
    conn = op.get_bind()

    # Drop taxonomy tables
    conn.execute(sa.text("DROP TABLE IF EXISTS taxonomy_terms;"))
    conn.execute(sa.text("DROP TABLE IF EXISTS taxonomies;"))

    # Remove new columns from document_content
    for col in ["classification", "document_type", "file_type", "file_path"]:
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

    # Restore old constraint name if document_content still exists
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'uq_document_content_source_url'
                  AND table_name = 'document_content'
            ) THEN
                ALTER TABLE document_content
                    RENAME CONSTRAINT uq_document_content_source_url
                    TO uq_scraped_content_source_url;
            END IF;
        END
        $$;
    """))

    # Rename back
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'document_content'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'scraped_contents'
            ) THEN
                ALTER TABLE document_content RENAME TO scraped_contents;
            END IF;
        END
        $$;
    """))
