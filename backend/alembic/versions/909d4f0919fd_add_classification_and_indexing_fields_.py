"""Add classification and indexing fields to Document model

Revision ID: 909d4f0919fd
Revises: f6a7b8c9d0e1
Create Date: 2026-03-31 13:54:32.524254

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '909d4f0919fd'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('classification', sa.JSON(), nullable=True))
    op.add_column('documents', sa.Column('classification_taxonomy_version', sa.Integer(), nullable=True))
    op.add_column('documents', sa.Column('indexed_at', sa.DateTime(), nullable=True))
    op.add_column('documents', sa.Column('error_message', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('documents', 'error_message')
    op.drop_column('documents', 'indexed_at')
    op.drop_column('documents', 'classification_taxonomy_version')
    op.drop_column('documents', 'classification')
