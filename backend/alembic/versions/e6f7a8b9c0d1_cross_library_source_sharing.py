"""Cross-library source sharing — junction table + nullable library embedding.

Replaces sources.library_id (single FK) with library_sources junction,
allowing a source to belong to multiple libraries. Makes library embedding
config nullable so the first source added locks in the model.

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-04-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Create junction table
    op.create_table(
        "library_sources",
        sa.Column("library_id", sa.String(36), sa.ForeignKey("libraries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("library_id", "source_id", name="pk_library_sources"),
    )
    op.create_index("ix_library_sources_library_id", "library_sources", ["library_id"])
    op.create_index("ix_library_sources_source_id", "library_sources", ["source_id"])

    # 2) Backfill from sources.library_id
    op.execute(
        """
        INSERT INTO library_sources (library_id, source_id, created_at)
        SELECT library_id, id, COALESCE(created_at, NOW())
        FROM sources
        WHERE library_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )

    # 3) Drop the old FK column
    # Names of the FK constraint and index vary by history; use IF EXISTS guards.
    op.execute("ALTER TABLE sources DROP CONSTRAINT IF EXISTS sources_library_id_fkey")
    op.execute("DROP INDEX IF EXISTS ix_sources_library_id")
    with op.batch_alter_table("sources") as batch:
        batch.drop_column("library_id")

    # 4) Make library embedding fields nullable (first source locks them in)
    op.alter_column("libraries", "embedding_provider", existing_type=sa.String(50), nullable=True)
    op.alter_column("libraries", "embedding_model", existing_type=sa.String(100), nullable=True)


def downgrade() -> None:
    # Re-add the column (nullable; data will be re-denormalized from junction best-effort)
    op.add_column(
        "sources",
        sa.Column("library_id", sa.String(36), sa.ForeignKey("libraries.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_sources_library_id", "sources", ["library_id"])

    # Best-effort denormalize — picks the earliest-created binding per source.
    # Lossy for any source bound to multiple libraries. Accepted tradeoff for a downgrade.
    op.execute(
        """
        UPDATE sources s
        SET library_id = ls.library_id
        FROM (
            SELECT DISTINCT ON (source_id) source_id, library_id
            FROM library_sources
            ORDER BY source_id, created_at ASC
        ) ls
        WHERE s.id = ls.source_id
        """
    )

    # Restore NOT NULL on library embedding fields (rows with NULL must be set first)
    op.execute(
        """
        UPDATE libraries
        SET embedding_provider = 'ollama', embedding_model = 'qwen3-embedding:4b'
        WHERE embedding_provider IS NULL OR embedding_model IS NULL
        """
    )
    op.alter_column("libraries", "embedding_provider", existing_type=sa.String(50), nullable=False)
    op.alter_column("libraries", "embedding_model", existing_type=sa.String(100), nullable=False)

    op.drop_index("ix_library_sources_source_id", table_name="library_sources")
    op.drop_index("ix_library_sources_library_id", table_name="library_sources")
    op.drop_table("library_sources")
