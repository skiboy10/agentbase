"""Tests for QuestionSetService."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Library, QuestionSet, Question, EvalRun, EvalResult
from app.services.evaluation import QuestionSetService


@pytest.fixture
async def library(db_session: AsyncSession) -> Library:
    lib = Library(name="ACME Docs", collection_name="kb_acme_test")
    db_session.add(lib)
    await db_session.commit()
    return lib


class TestQuestionSetService:
    async def test_create_and_list(self, db_session: AsyncSession, library):
        svc = QuestionSetService(db_session)
        qs = await svc.create_set(library_id=library.id, name="Core questions")
        sets = await svc.list_sets(library_id=library.id)
        assert [s.id for s in sets] == [qs.id]

    async def test_add_manual_question_is_active(self, db_session, library):
        svc = QuestionSetService(db_session)
        qs = await svc.create_set(library_id=library.id, name="Core")
        q = await svc.add_question(
            question_set_id=qs.id,
            question_text="What is the ACME onboarding flow?",
            expected_criteria="Mentions the three onboarding stages",
            origin="manual",
        )
        assert q.status == "active"
        assert q.origin == "manual"

    async def test_generated_question_starts_draft(self, db_session, library):
        svc = QuestionSetService(db_session)
        qs = await svc.create_set(library_id=library.id, name="Core")
        q = await svc.add_question(
            question_set_id=qs.id, question_text="Q?", origin="generated"
        )
        assert q.status == "draft"

    async def test_approve_draft(self, db_session, library):
        svc = QuestionSetService(db_session)
        qs = await svc.create_set(library_id=library.id, name="Core")
        q = await svc.add_question(question_set_id=qs.id, question_text="Q?", origin="generated")
        updated = await svc.update_question(q.id, status="active")
        assert updated.status == "active"

    async def test_delete_question_without_results_hard_deletes(self, db_session, library):
        svc = QuestionSetService(db_session)
        qs = await svc.create_set(library_id=library.id, name="Core")
        q = await svc.add_question(question_set_id=qs.id, question_text="Q?")
        outcome = await svc.delete_question(q.id)
        assert outcome == "deleted"
        assert await svc.get_question(q.id) is None

    async def test_delete_question_with_results_archives(self, db_session, library):
        svc = QuestionSetService(db_session)
        qs = await svc.create_set(library_id=library.id, name="Core")
        q = await svc.add_question(question_set_id=qs.id, question_text="Q?")
        run = EvalRun(target_type="library", target_id=library.id,
                      target_label=library.name, question_set_id=qs.id)
        db_session.add(run)
        await db_session.flush()
        db_session.add(EvalResult(eval_run_id=run.id, question_id=q.id))
        await db_session.commit()

        outcome = await svc.delete_question(q.id)
        assert outcome == "archived"
        archived = await svc.get_question(q.id)
        assert archived.status == "archived"

    async def test_delete_set_with_results_succeeds(self, db_session, library):
        """Deleting a set with eval history deletes runs first so results
        never outlive their questions (FK is CASCADE since rev d6e7f8a9b0c1,
        but the ordering keeps this safe on not-yet-migrated databases)."""
        svc = QuestionSetService(db_session)
        qs = await svc.create_set(library_id=library.id, name="Core")
        q = await svc.add_question(question_set_id=qs.id, question_text="Q?")
        run = EvalRun(target_type="library", target_id=library.id,
                      target_label=library.name, question_set_id=qs.id)
        db_session.add(run)
        await db_session.flush()
        db_session.add(EvalResult(eval_run_id=run.id, question_id=q.id))
        await db_session.commit()

        assert await svc.delete_set(qs.id) is True
        assert await svc.get_set(qs.id) is None
        assert await svc.get_question(q.id) is None

    async def test_update_question_can_clear_optional_field(self, db_session, library):
        """Review fix: a present key with None clears the field."""
        svc = QuestionSetService(db_session)
        qs = await svc.create_set(library_id=library.id, name="Core")
        q = await svc.add_question(question_set_id=qs.id, question_text="Q?",
                                   expected_criteria="Some criteria")
        updated = await svc.update_question(q.id, expected_criteria=None)
        assert updated.expected_criteria is None
        # Omitted keys stay untouched
        assert updated.question_text == "Q?"

    async def test_question_counts_grouped_by_status(self, db_session, library):
        svc = QuestionSetService(db_session)
        qs = await svc.create_set(library_id=library.id, name="Core")
        await svc.add_question(question_set_id=qs.id, question_text="A?")          # active
        await svc.add_question(question_set_id=qs.id, question_text="B?")          # active
        await svc.add_question(question_set_id=qs.id, question_text="C?",
                               origin="generated")                                  # draft
        counts = await svc.question_counts([qs.id])
        assert counts[qs.id] == {"active": 2, "draft": 1}
        assert await svc.question_counts([]) == {}
