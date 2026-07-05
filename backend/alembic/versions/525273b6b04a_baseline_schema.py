"""baseline schema

Revision ID: 525273b6b04a
Revises:
Create Date: 2026-03-17 12:21:43.770421

This is the baseline migration for Agentbase core tables.
For EXISTING databases: run 'alembic stamp head' to mark as current.
For NEW databases: this migration creates all core tables.

Tables managed by extensions (migration_*, test_*, conversations, etc.)
are NOT included here — extensions manage their own schemas.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '525273b6b04a'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Projects
    op.create_table('projects',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('instructions', sa.Text(), nullable=True),
        sa.Column('knowledge_provider', sa.String(50), nullable=True),
        sa.Column('knowledge_model', sa.String(100), nullable=True),
        sa.Column('coding_provider', sa.String(50), nullable=True),
        sa.Column('coding_model', sa.String(100), nullable=True),
        sa.Column('settings', sa.JSON(), nullable=True),
    )

    # Provider configs
    op.create_table('provider_configs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('provider_name', sa.String(50), unique=True, nullable=False),
        sa.Column('api_key_encrypted', sa.Text(), nullable=True),
        sa.Column('base_url', sa.String(500), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('disabled_models', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )

    # Knowledge sources
    op.create_table('knowledge_sources',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('source_type', sa.String(20), nullable=False),
        sa.Column('source_path', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), default='pending'),
        sa.Column('last_indexed', sa.DateTime(), nullable=True),
        sa.Column('document_count', sa.Integer(), default=0),
        sa.Column('chunk_count', sa.Integer(), default=0),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('progress', sa.Integer(), default=0),
        sa.Column('progress_total', sa.Integer(), default=0),
        sa.Column('progress_message', sa.String(500), nullable=True),
        sa.Column('progress_updated_at', sa.DateTime(), nullable=True),
        sa.Column('collection_name', sa.String(255), nullable=True),
        sa.Column('embedding_provider', sa.String(50), nullable=True),
        sa.Column('embedding_model', sa.String(100), nullable=True),
        sa.Column('embedding_dimensions', sa.Integer(), nullable=True),
        sa.Column('selected_urls', sa.Text(), nullable=True),
        sa.Column('selected_files', sa.Text(), nullable=True),
        sa.Column('custom_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )

    # Indexing logs
    op.create_table('indexing_logs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('source_id', sa.String(36), sa.ForeignKey('knowledge_sources.id', ondelete='CASCADE'), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('scrape_duration_ms', sa.Integer(), nullable=True),
        sa.Column('embed_duration_ms', sa.Integer(), nullable=True),
        sa.Column('content_length', sa.Integer(), nullable=True),
        sa.Column('chunk_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('source_id', 'url', name='uq_indexing_log_source_url'),
    )

    # Scraped content
    op.create_table('scraped_contents',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('source_id', sa.String(36), sa.ForeignKey('knowledge_sources.id', ondelete='CASCADE'), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('title', sa.String(500), nullable=True),
        sa.Column('raw_content', sa.Text(), nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('content_length', sa.Integer(), default=0),
        sa.Column('scraped_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('source_id', 'url', name='uq_scraped_content_source_url'),
    )

    # Model assignments
    op.create_table('model_assignments',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=True),
        sa.Column('task_type', sa.String(20), nullable=False),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('model', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('task_type', 'project_id', name='uq_model_assignment_task_project'),
    )
    # Partial unique index for global assignments (project_id IS NULL)
    op.create_index(
        'ix_model_assignment_task_global', 'model_assignments',
        ['task_type'], unique=True,
        postgresql_where=sa.text('project_id IS NULL'),
    )

    # Prompts
    op.create_table('prompts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('task_type', sa.String(50), nullable=False),
        sa.Column('system_prompt', sa.Text(), nullable=False),
        sa.Column('rag_context_template', sa.Text(), nullable=True),
        sa.Column('use_rag', sa.Boolean(), default=True),
        sa.Column('is_default', sa.Boolean(), default=False),
        sa.Column('version', sa.Integer(), default=1),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )

    # Project-knowledge junction
    op.create_table('project_knowledge_sources',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('source_id', sa.String(36), sa.ForeignKey('knowledge_sources.id', ondelete='CASCADE'), nullable=False),
        sa.Column('assigned_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('project_id', 'source_id', name='uq_project_knowledge_source'),
    )

    # Project-agent junction
    op.create_table('project_agents',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('agent_id', sa.String(36), sa.ForeignKey('agents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('assigned_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('project_id', 'agent_id', name='uq_project_agent'),
    )

    # Agents
    op.create_table('agents',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=True),
        sa.Column('agent_id', sa.String(255), unique=True, nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('system_prompt', sa.Text(), nullable=False),
        sa.Column('model_provider', sa.String(50), nullable=False),
        sa.Column('model_name', sa.String(100), nullable=False),
        sa.Column('temperature', sa.Float(), default=0.7),
        sa.Column('use_rag', sa.Boolean(), default=True),
        sa.Column('rag_top_k', sa.Integer(), default=5),
        sa.Column('skills', sa.JSON(), nullable=True),
        sa.Column('is_public', sa.Boolean(), default=False),
        sa.Column('api_key_hash', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )

    # Agent-knowledge junction
    op.create_table('agent_knowledge_sources',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('agent_id', sa.String(36), sa.ForeignKey('agents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('knowledge_source_id', sa.String(36), sa.ForeignKey('knowledge_sources.id', ondelete='CASCADE'), nullable=False),
        sa.Column('assigned_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('agent_id', 'knowledge_source_id', name='uq_agent_knowledge_source'),
    )

    # Experimental indexes
    op.create_table('experimental_indexes',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('source_id', sa.String(36), sa.ForeignKey('knowledge_sources.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('embedding_provider', sa.String(50), nullable=False),
        sa.Column('embedding_model', sa.String(100), nullable=False),
        sa.Column('embedding_dimensions', sa.Integer(), nullable=True),
        sa.Column('chunk_size', sa.Integer(), default=512),
        sa.Column('chunk_overlap', sa.Integer(), default=50),
        sa.Column('collection_name', sa.String(255), nullable=False),
        sa.Column('status', sa.String(50), default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('document_count', sa.Integer(), default=0),
        sa.Column('chunk_count', sa.Integer(), default=0),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('indexed_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('experimental_indexes')
    op.drop_table('agent_knowledge_sources')
    op.drop_table('agents')
    op.drop_table('project_agents')
    op.drop_table('project_knowledge_sources')
    op.drop_table('prompts')
    op.drop_index('ix_model_assignment_task_global', table_name='model_assignments')
    op.drop_table('model_assignments')
    op.drop_table('scraped_contents')
    op.drop_table('indexing_logs')
    op.drop_table('knowledge_sources')
    op.drop_table('provider_configs')
    op.drop_table('projects')
