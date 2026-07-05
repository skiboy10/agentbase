"""add api_keys table

Revision ID: b1a3e7f94c20
Revises: 2fc65ef320f8
Create Date: 2026-03-24 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b1a3e7f94c20'
down_revision: Union[str, None] = '2fc65ef320f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('api_keys',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('key_hash', sa.String(length=64), nullable=False),
        sa.Column('key_prefix', sa.String(length=10), nullable=False),
        sa.Column('scopes', sa.JSON(), nullable=False),
        sa.Column('rate_limit_rpm', sa.Integer(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key_hash', name='uq_api_keys_key_hash')
    )
    op.create_index('ix_api_keys_is_active', 'api_keys', ['is_active'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_api_keys_is_active', table_name='api_keys')
    op.drop_table('api_keys')
