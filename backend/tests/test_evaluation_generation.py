"""Tests for question generation."""
import json
import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Library, Document, QuestionSet
from app.services.evaluation import QuestionSetService
from app.services.evaluation.generation import (
    sample_documents, parse_generated_questions, execute_question_generation,
)


@pytest.fixture
async def library_with_docs(db_session: AsyncSession) -> Library:
    lib = Library(name="ACME Docs", collection_name="kb_acme_gen")
    db_session.add(lib)
    await db_session.flush()
    for i in range(12):
        db_session.add(Document(
            library_id=lib.id, document_id=f"/tmp/acme/doc{i}.md",
            title=f"ACME Guide {i}", full_text=f"Content of guide {i}. " * 50,
            classification={"topic": "alpha" if i % 2 == 0 else "beta"} if i < 8 else None,
        ))
    await db_session.commit()
    return lib


class TestSampling:
    async def test_sample_stratifies_across_classification(self, db_session, library_with_docs):
        docs = await sample_documents(db_session, library_with_docs.id, count=6)
        assert len(docs) == 6
        topics = {(d.classification or {}).get("topic") for d in docs}
        assert len(topics) >= 2  # not all from one stratum

    async def test_sample_works_without_classification(self, db_session):
        lib = Library(name="Bare", collection_name="kb_bare_gen")
        db_session.add(lib)
        await db_session.flush()
        for i in range(3):
            db_session.add(Document(library_id=lib.id, document_id=f"d{i}",
                                    full_text="text " * 20))
        await db_session.commit()
        docs = await sample_documents(db_session, lib.id, count=5)
        assert len(docs) == 3  # capped at available


class TestParsing:
    def test_parse_valid_json(self):
        raw = json.dumps([{"question": "What is X?",
                           "expected_criteria": "Defines X"}])
        out = parse_generated_questions(raw)
        assert out[0]["question"] == "What is X?"

    def test_parse_json_in_code_fence(self):
        raw = '```json\n[{"question": "Q?", "expected_criteria": "C"}]\n```'
        assert parse_generated_questions(raw)[0]["question"] == "Q?"

    def test_parse_garbage_returns_empty(self):
        assert parse_generated_questions("not json at all") == []


class TestExecution:
    async def test_generation_creates_draft_questions(self, db_session, library_with_docs):
        svc = QuestionSetService(db_session)
        qs = await svc.create_set(library_id=library_with_docs.id, name="Gen")
        fake_response = json.dumps([
            {"question": "What does Guide 1 cover?", "expected_criteria": "Covers guide 1"},
            {"question": "How does ACME onboard?", "expected_criteria": "Three stages"},
        ])
        with patch("app.services.evaluation.generation._call_generation_llm",
                   new=AsyncMock(return_value=fake_response)):
            created = await execute_question_generation(
                db_session, question_set_id=qs.id, questions_per_doc=2, doc_sample_size=2,
            )
        assert created >= 2
        drafts = await svc.list_questions(qs.id, status="draft")
        assert all(q.origin == "generated" for q in drafts)
        assert all(q.expected_document_ids for q in drafts)  # source doc recorded


class TestCountControl:
    """`count` (issue #194) caps the total and drives document sampling."""

    @staticmethod
    def _fake_response(n: int) -> str:
        return json.dumps([
            {"question": f"Q{i}?", "expected_criteria": f"C{i}"} for i in range(n)
        ])

    async def test_count_caps_created_questions(self, db_session, library_with_docs):
        svc = QuestionSetService(db_session)
        qs = await svc.create_set(library_id=library_with_docs.id, name="Capped")
        # 3 questions per LLM call; count=5 must stop mid-document
        with patch("app.services.evaluation.generation._call_generation_llm",
                   new=AsyncMock(return_value=self._fake_response(3))):
            created = await execute_question_generation(
                db_session, question_set_id=qs.id, questions_per_doc=3, count=5,
            )
        assert created == 5
        assert len(await svc.list_questions(qs.id, status="draft")) == 5

    async def test_count_overrides_doc_sample_size(self, db_session, library_with_docs):
        svc = QuestionSetService(db_session)
        qs = await svc.create_set(library_id=library_with_docs.id, name="Sampled")
        mock_llm = AsyncMock(return_value=self._fake_response(3))
        # count=6 at 3/doc -> ceil(6/3) = 2 documents sampled, not the
        # doc_sample_size default of 10
        with patch("app.services.evaluation.generation._call_generation_llm",
                   new=mock_llm):
            created = await execute_question_generation(
                db_session, question_set_id=qs.id, questions_per_doc=3, count=6,
            )
        assert created == 6
        assert mock_llm.await_count == 2

    async def test_without_count_legacy_sampling_applies(self, db_session,
                                                         library_with_docs):
        svc = QuestionSetService(db_session)
        qs = await svc.create_set(library_id=library_with_docs.id, name="Legacy")
        mock_llm = AsyncMock(return_value=self._fake_response(1))
        with patch("app.services.evaluation.generation._call_generation_llm",
                   new=mock_llm):
            created = await execute_question_generation(
                db_session, question_set_id=qs.id,
                questions_per_doc=1, doc_sample_size=4,
            )
        assert created == 4
        assert mock_llm.await_count == 4
