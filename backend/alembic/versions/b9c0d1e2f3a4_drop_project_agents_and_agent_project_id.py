"""drop project_agents table and agents.project_id column

Removes the project↔agent assignment infrastructure now that Projects are
deprecated (#56) and every agent is just an agent. The project_agents junction
table and the agents.project_id foreign-key column are no longer referenced by
any application code.

Revision ID: b9c0d1e2f3a4
Revises: f7a8b9c0d1e2
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa


revision = 'b9c0d1e2f3a4'
down_revision = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table('project_agents')
    # Dropping the column also drops its FK constraint and any index on it
    # (e.g. ix_agents_project_id from ORM index=True) server-side in Postgres.
    op.drop_column('agents', 'project_id')


def downgrade() -> None:
    # Restore agents.project_id with the original FK + index
    # (matches the 525273b6b04a baseline definition plus ORM index=True).
    op.add_column('agents', sa.Column('project_id', sa.String(length=36), nullable=True))
    op.create_foreign_key(
        'agents_project_id_fkey', 'agents', 'projects',
        ['project_id'], ['id'],
    )
    op.create_index('ix_agents_project_id', 'agents', ['project_id'])
    op.create_table(
        'project_agents',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('agent_id', sa.String(length=36), nullable=False),
        sa.Column('assigned_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'agent_id', name='uq_project_agent'),
    )
