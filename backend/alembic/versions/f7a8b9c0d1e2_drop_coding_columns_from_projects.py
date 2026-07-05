"""drop coding_provider and coding_model columns from projects

Removes the legacy coding_provider and coding_model columns from the projects
table. These were introduced with the original coding-task-type feature (#122),
which has been fully removed. Both columns were nullable and unused; no data
migration is required.

Revision ID: f7a8b9c0d1e2
Revises: e7f8a9b0c1d2
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa


revision = 'f7a8b9c0d1e2'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column('projects', 'coding_provider')
    op.drop_column('projects', 'coding_model')


def downgrade() -> None:
    op.add_column('projects', sa.Column('coding_provider', sa.String(length=50), nullable=True))
    op.add_column('projects', sa.Column('coding_model', sa.String(length=100), nullable=True))
