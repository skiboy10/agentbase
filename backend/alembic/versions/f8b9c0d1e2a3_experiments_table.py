"""experiments table (drop source-scoped experimental_indexes)

Revision ID: f8b9c0d1e2a3
Revises: ed7d2cc3cd23
Create Date: 2026-06-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8b9c0d1e2a3'
down_revision: Union[str, None] = 'ed7d2cc3cd23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Dead source-scoped experiments feature — rows (if any) are dev artifacts.
    # Dropped unconditionally; documented in release notes (same rationale as
    # the test_* framework drop in ed7d2cc3cd23).
    op.drop_table('experimental_indexes')

    op.create_table(
        'experiments',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('library_id', sa.String(36), sa.ForeignKey('libraries.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('agent_id', sa.String(36), sa.ForeignKey('agents.id', ondelete='CASCADE'), nullable=True, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('experiment_type', sa.String(20), nullable=False, server_default='pipeline'),
        sa.Column('overrides', sa.JSON(), nullable=True),
        sa.Column('shadow_collection', sa.String(255), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='ready', index=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('promoted_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('experiments')
    op.create_table(
        'experimental_indexes',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('source_id', sa.String(36), sa.ForeignKey('sources.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('embedding_provider', sa.String(50), nullable=False),
        sa.Column('embedding_model', sa.String(100), nullable=False),
        sa.Column('embedding_dimensions', sa.Integer(), nullable=True),
        sa.Column('chunk_size', sa.Integer(), nullable=False, server_default='512'),
        sa.Column('chunk_overlap', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('collection_name', sa.String(255), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('document_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('chunk_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('indexed_at', sa.DateTime(), nullable=True),
    )
