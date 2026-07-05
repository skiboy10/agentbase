"""add jobs table

Revision ID: a9f01dc0cf95
Revises: 90d85a4e57d6
Create Date: 2026-03-17 12:54:24.823046

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a9f01dc0cf95'
down_revision: Union[str, None] = '90d85a4e57d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('jobs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('job_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False),
        sa.Column('max_retries', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_jobs_job_type', 'jobs', ['job_type'], unique=False)
    op.create_index('ix_jobs_project_id', 'jobs', ['project_id'], unique=False)
    op.create_index('ix_jobs_status', 'jobs', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_jobs_status', table_name='jobs')
    op.drop_index('ix_jobs_project_id', table_name='jobs')
    op.drop_index('ix_jobs_job_type', table_name='jobs')
    op.drop_table('jobs')
