"""Question set CRUD and curation lifecycle."""
from typing import Optional
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models import QuestionSet, Question, EvalRun, EvalResult

logger = structlog.get_logger()

VALID_STATUSES = {"draft", "active", "archived", "stale"}


class QuestionSetService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_set(self, library_id: str, name: str,
                         description: Optional[str] = None) -> QuestionSet:
        qs = QuestionSet(library_id=library_id, name=name, description=description)
        self.db.add(qs)
        await self.db.commit()
        await self.db.refresh(qs)
        return qs

    async def list_sets(self, library_id: Optional[str] = None) -> list[QuestionSet]:
        stmt = select(QuestionSet).order_by(QuestionSet.created_at.desc())
        if library_id:
            stmt = stmt.where(QuestionSet.library_id == library_id)
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_set(self, set_id: str) -> Optional[QuestionSet]:
        return await self.db.get(QuestionSet, set_id)

    async def update_set(self, set_id: str, **fields) -> Optional[QuestionSet]:
        """Update a set. Pass only the fields to change (callers use
        exclude_unset); description may be explicitly set to None to clear."""
        qs = await self.db.get(QuestionSet, set_id)
        if not qs:
            return None
        for k, v in fields.items():
            if k == "name" and v is not None:
                setattr(qs, k, v)
            elif k == "description":
                setattr(qs, k, v)
        await self.db.commit()
        await self.db.refresh(qs)
        return qs

    async def delete_set(self, set_id: str) -> bool:
        qs = await self.db.get(QuestionSet, set_id)
        if not qs:
            return False
        # Delete the set's runs first (cascades their results). Otherwise the
        # ORM cascades question deletion before run deletion and trips the
        # RESTRICT FK on eval_results.question_id.
        runs = (await self.db.execute(
            select(EvalRun).where(EvalRun.question_set_id == set_id)
        )).scalars().all()
        for run in runs:
            await self.db.delete(run)
        await self.db.flush()
        await self.db.delete(qs)
        await self.db.commit()
        return True

    async def question_counts(self, set_ids: list[str]) -> dict[str, dict[str, int]]:
        """Per-set question counts grouped by status: {set_id: {status: n}}."""
        if not set_ids:
            return {}
        stmt = (select(Question.question_set_id, Question.status,
                       sa_func.count(Question.id))
                .where(Question.question_set_id.in_(set_ids))
                .group_by(Question.question_set_id, Question.status))
        out: dict[str, dict[str, int]] = {}
        for set_id, status, n in (await self.db.execute(stmt)).all():
            out.setdefault(set_id, {})[status] = n
        return out

    async def list_questions(self, question_set_id: str,
                             status: Optional[str] = None) -> list[Question]:
        stmt = (select(Question)
                .where(Question.question_set_id == question_set_id)
                .order_by(Question.created_at.asc()))
        if status:
            stmt = stmt.where(Question.status == status)
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_question(self, question_id: str) -> Optional[Question]:
        return await self.db.get(Question, question_id)

    async def add_question(self, question_set_id: str, question_text: str,
                           expected_criteria: Optional[str] = None,
                           expected_document_ids: Optional[list] = None,
                           tags: Optional[list] = None,
                           origin: str = "manual") -> Question:
        # Manual questions are trusted (active); generated ones await curation (draft)
        status = "active" if origin == "manual" else "draft"
        q = Question(
            question_set_id=question_set_id,
            question_text=question_text,
            expected_criteria=expected_criteria,
            expected_document_ids=expected_document_ids,
            tags=tags,
            origin=origin,
            status=status,
        )
        self.db.add(q)
        await self.db.commit()
        await self.db.refresh(q)
        return q

    async def update_question(self, question_id: str, **fields) -> Optional[Question]:
        """Update a question. Pass only the fields to change (callers use
        exclude_unset). Optional fields (expected_criteria, expected_document_ids,
        tags) may be explicitly set to None to clear; question_text and status
        may not be None."""
        q = await self.db.get(Question, question_id)
        if not q:
            return None
        if "status" in fields:
            if fields["status"] not in VALID_STATUSES:
                raise ValueError(f"Invalid status: {fields['status']}")
        for k in ("expected_criteria", "expected_document_ids", "tags"):
            if k in fields:
                setattr(q, k, fields[k])
        for k in ("question_text", "status"):
            if k in fields and fields[k] is not None:
                setattr(q, k, fields[k])
        await self.db.commit()
        await self.db.refresh(q)
        return q

    async def delete_question(self, question_id: str) -> Optional[str]:
        """Delete a question. Returns 'deleted', 'archived' (if it has results),
        or None if not found. Questions with EvalResults are archived to
        preserve scorecard history (design doc §2)."""
        q = await self.db.get(Question, question_id)
        if not q:
            return None
        has_results = (await self.db.execute(
            select(sa_func.count(EvalResult.id)).where(EvalResult.question_id == question_id)
        )).scalar_one() > 0
        if has_results:
            q.status = "archived"
            await self.db.commit()
            return "archived"
        await self.db.delete(q)
        await self.db.commit()
        return "deleted"
