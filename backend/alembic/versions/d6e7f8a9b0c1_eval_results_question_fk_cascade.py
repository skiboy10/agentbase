"""eval_results.question_id FK: RESTRICT -> CASCADE

RESTRICT is checked immediately by PostgreSQL, so cascade-deleting a
question_set (directly, or via its library) failed with an FK violation
on questions -> eval_results even though the eval_results rows were about
to be cascade-deleted through eval_runs anyway. The archive-instead-of-
delete rule for individual questions with results is enforced in the
service layer (QuestionSetService.delete_question), not by this FK.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-07-08

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd6e7f8a9b0c1'
down_revision: Union[str, None] = 'c5d6e7f8a9b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('eval_results_question_id_fkey', 'eval_results', type_='foreignkey')
    op.create_foreign_key(
        'eval_results_question_id_fkey',
        'eval_results', 'questions',
        ['question_id'], ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint('eval_results_question_id_fkey', 'eval_results', type_='foreignkey')
    op.create_foreign_key(
        'eval_results_question_id_fkey',
        'eval_results', 'questions',
        ['question_id'], ['id'],
        ondelete='RESTRICT',
    )
