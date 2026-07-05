"""add FK indexes

Revision ID: 90d85a4e57d6
Revises: 525273b6b04a
Create Date: 2026-03-17 12:24:35.766388

Adds indexes on foreign key columns for query performance.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '90d85a4e57d6'
down_revision: Union[str, None] = '525273b6b04a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_knowledge_sources_project_id', 'knowledge_sources', ['project_id'], unique=False)
    op.create_index('ix_indexing_logs_source_id', 'indexing_logs', ['source_id'], unique=False)
    op.create_index('ix_scraped_contents_source_id', 'scraped_contents', ['source_id'], unique=False)
    op.create_index('ix_prompts_project_id', 'prompts', ['project_id'], unique=False)
    op.create_index('ix_experimental_indexes_source_id', 'experimental_indexes', ['source_id'], unique=False)
    # agents.project_id already has idx_agents_project_id from extensions


def downgrade() -> None:
    op.drop_index('ix_experimental_indexes_source_id', table_name='experimental_indexes')
    op.drop_index('ix_prompts_project_id', table_name='prompts')
    op.drop_index('ix_scraped_contents_source_id', table_name='scraped_contents')
    op.drop_index('ix_indexing_logs_source_id', table_name='indexing_logs')
    op.drop_index('ix_knowledge_sources_project_id', table_name='knowledge_sources')
