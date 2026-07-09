"""evaluation tables, drop test framework

Revision ID: ed7d2cc3cd23
Revises: b9c0d1e2f3a4
Create Date: 2026-06-11 13:06:57.573750

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ed7d2cc3cd23'
down_revision: Union[str, None] = 'b9c0d1e2f3a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Dead test framework — never had a UI; rows (if any) are dev artifacts.
    # IF EXISTS: these extension-era tables never exist on fresh installs (#17).
    op.execute('DROP TABLE IF EXISTS test_case_results')
    op.execute('DROP TABLE IF EXISTS test_runs')
    op.execute('DROP TABLE IF EXISTS test_cases')
    op.execute('DROP TABLE IF EXISTS test_suites')

    op.create_table(
        'question_sets',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('library_id', sa.String(36), sa.ForeignKey('libraries.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        'questions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('question_set_id', sa.String(36), sa.ForeignKey('question_sets.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('question_text', sa.Text(), nullable=False),
        sa.Column('expected_criteria', sa.Text(), nullable=True),
        sa.Column('expected_document_ids', sa.JSON(), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('origin', sa.String(20), nullable=False, server_default='manual'),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft', index=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        'eval_runs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('target_type', sa.String(20), nullable=False),
        sa.Column('target_id', sa.String(36), nullable=False, index=True),
        sa.Column('target_label', sa.String(255), nullable=False),
        sa.Column('question_set_id', sa.String(36), sa.ForeignKey('question_sets.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('run_type', sa.String(20), nullable=False, server_default='retrieval'),
        sa.Column('config_snapshot', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending', index=True),
        sa.Column('metrics_summary', sa.JSON(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        'eval_results',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('eval_run_id', sa.String(36), sa.ForeignKey('eval_runs.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('question_id', sa.String(36), sa.ForeignKey('questions.id', ondelete='RESTRICT'), nullable=False, index=True),
        sa.Column('retrieved', sa.JSON(), nullable=True),
        sa.Column('retrieval_metrics', sa.JSON(), nullable=True),
        sa.Column('answer_text', sa.Text(), nullable=True),
        sa.Column('judge_scores', sa.JSON(), nullable=True),
        sa.Column('judge_rationale', sa.Text(), nullable=True),
        sa.Column('passed', sa.Boolean(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('eval_results')
    op.drop_table('eval_runs')
    op.drop_table('questions')
    op.drop_table('question_sets')
    # test_* tables intentionally not recreated (dead feature)
