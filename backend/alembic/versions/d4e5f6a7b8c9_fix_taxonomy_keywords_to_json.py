"""fix taxonomy_terms keywords column to JSON (was TEXT[])

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-03-28 00:01:00.000000

The keywords column was initially created as TEXT[] (PostgreSQL ARRAY).
Changing to JSON for cross-database compatibility (SQLite in tests).
Uses USING clause to cast existing arrays to JSON.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Only alter if the column is currently ARRAY type (TEXT[])
    # If it's already JSON (idempotent re-run), skip.
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'taxonomy_terms'
                  AND column_name = 'keywords'
                  AND data_type = 'ARRAY'
            ) THEN
                ALTER TABLE taxonomy_terms
                    ALTER COLUMN keywords TYPE JSON
                    USING to_json(keywords);
            END IF;
        END
        $$;
    """))


def downgrade() -> None:
    conn = op.get_bind()

    # Revert JSON → TEXT[] (data may be lossy if keywords had non-string values)
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'taxonomy_terms'
                  AND column_name = 'keywords'
                  AND data_type = 'json'
            ) THEN
                ALTER TABLE taxonomy_terms
                    ALTER COLUMN keywords TYPE TEXT[]
                    USING ARRAY(SELECT jsonb_array_elements_text(keywords::jsonb));
            END IF;
        END
        $$;
    """))
