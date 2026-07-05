"""add metadata schemas and extend knowledge source

Revision ID: 2fc65ef320f8
Revises: a9f01dc0cf95
Create Date: 2026-03-17 13:15:52.194692

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '2fc65ef320f8'
down_revision: Union[str, None] = 'a9f01dc0cf95'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create metadata schemas table
    op.create_table('knowledge_metadata_schemas',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('fields', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    # Extend knowledge_sources with metadata schema reference and default metadata
    op.add_column('knowledge_sources', sa.Column('metadata_schema_id', sa.String(length=36), nullable=True))
    op.add_column('knowledge_sources', sa.Column('default_metadata', sa.JSON(), nullable=True))
    op.create_index('ix_knowledge_sources_metadata_schema_id', 'knowledge_sources', ['metadata_schema_id'], unique=False)
    op.create_foreign_key(
        'fk_knowledge_sources_metadata_schema',
        'knowledge_sources', 'knowledge_metadata_schemas',
        ['metadata_schema_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('fk_knowledge_sources_metadata_schema', 'knowledge_sources', type_='foreignkey')
    op.drop_index('ix_knowledge_sources_metadata_schema_id', table_name='knowledge_sources')
    op.drop_column('knowledge_sources', 'default_metadata')
    op.drop_column('knowledge_sources', 'metadata_schema_id')
    op.drop_table('knowledge_metadata_schemas')
