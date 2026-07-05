"""Generate draft questions from a library's own documents.

Sampling is stratified across classification topics when available
(falls back to recency-ordered sampling for unclassified libraries —
design doc §9)."""
import json
import math
import re
import random
from typing import Optional
from collections import defaultdict
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models import Document, QuestionSet, Prompt
from app.services.evaluation.question_sets import QuestionSetService

logger = structlog.get_logger()

MAX_DOC_CHARS = 4000  # context budget per sampled document

GENERATION_TEMPERATURE = 0.3
GENERATION_MAX_TOKENS = 1500

# Total-question-count control (issue #194). The historical default is
# questions_per_doc (3) x doc_sample_size (10) = 30; `count` makes that
# explicit and lets callers pick a validated total.
DEFAULT_QUESTION_COUNT = 30
GENERATION_COUNT_MIN = 5
GENERATION_COUNT_MAX = 50

# Default generation model when no ModelAssignment exists for task type
# 'question_generation'. Question drafting benefits from a larger local model
# than the enrichment classifier uses.
GENERATION_DEFAULT_PROVIDER = "ollama"
GENERATION_DEFAULT_MODEL = "gemma4:26b-mlx"

GENERATION_FALLBACK_PROMPT = """You are building an evaluation question set for a knowledge library.
Given a document, draft {n} questions a real user would plausibly ask that this
document answers. For each, state the facts a good answer must contain.

Return ONLY a JSON array: [{{"question": "...", "expected_criteria": "..."}}]"""


async def sample_documents(db: AsyncSession, library_id: str, count: int) -> list[Document]:
    stmt = select(Document).where(Document.library_id == library_id,
                                  Document.full_text.isnot(None),
                                  sa_func.length(Document.full_text) > 0)
    docs = list((await db.execute(stmt)).scalars().all())
    if len(docs) <= count:
        return docs
    # Stratify by classification topic where present
    strata: dict[str, list[Document]] = defaultdict(list)
    for d in docs:
        topic = (d.classification or {}).get("topic") or "__unclassified__"
        strata[topic].append(d)
    rng = random.Random(library_id)  # deterministic per library for testability
    picked: list[Document] = []
    keys = sorted(strata.keys())
    while len(picked) < count and any(strata[k] for k in keys):
        for k in keys:
            if strata[k] and len(picked) < count:
                picked.append(strata[k].pop(rng.randrange(len(strata[k]))))
    return picked


def parse_generated_questions(raw: str) -> list[dict]:
    """Parse the LLM response into [{question, expected_criteria}]. Tolerant of code fences."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Question generation: unparseable LLM output", head=text[:120])
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if isinstance(item, dict) and item.get("question"):
            out.append({"question": str(item["question"]),
                        "expected_criteria": str(item.get("expected_criteria") or "")})
    return out


async def _get_generation_prompt(db: AsyncSession, n: int) -> str:
    stmt = select(Prompt).where(Prompt.task_type == "question_generation",
                                Prompt.is_default == True)  # noqa: E712
    prompt = (await db.execute(stmt)).scalars().first()
    template = prompt.system_prompt if prompt else GENERATION_FALLBACK_PROMPT
    return template.replace("{n}", str(n))


async def _resolve_generation_model(db: AsyncSession) -> tuple[str, str]:
    """Resolve (provider, model) for question generation.

    Checks the global ModelAssignment for task type 'question_generation';
    falls back to GENERATION_DEFAULT_MODEL (onboard Ollama model)."""
    from app.models import ModelAssignment

    stmt = select(ModelAssignment).where(
        ModelAssignment.project_id.is_(None),
        ModelAssignment.task_type == "question_generation",
    )
    assignment = (await db.execute(stmt)).scalars().first()
    if assignment:
        return assignment.provider, assignment.model
    return GENERATION_DEFAULT_PROVIDER, GENERATION_DEFAULT_MODEL


async def _call_generation_llm(db: AsyncSession, system_prompt: str, doc_text: str) -> str:
    """Invoke the LLM. Mirrors EnrichmentService's provider call — see
    app/services/ingestion/enrichment.py. Kept separate for test mocking."""
    from app.providers.registry import get_registry
    from app.providers.base import ChatMessage, MessageRole

    provider_name, model = await _resolve_generation_model(db)

    registry = get_registry()
    # System instructions go via the system_prompt kwarg, not a SYSTEM-role
    # message: the Anthropic provider drops system messages from the list and
    # only reads the kwarg; all other providers honor the kwarg too.
    messages = [ChatMessage(role=MessageRole.USER, content=doc_text)]
    response = await registry.chat(
        provider_name=provider_name,
        model=model,
        messages=messages,
        temperature=GENERATION_TEMPERATURE,
        max_tokens=GENERATION_MAX_TOKENS,
        system_prompt=system_prompt,
    )
    return response.content


async def execute_question_generation(
    db: AsyncSession,
    question_set_id: str,
    questions_per_doc: int = 3,
    doc_sample_size: int = 10,
    count: Optional[int] = None,
) -> int:
    """Generate draft questions for a set. Returns count created.

    When `count` is set it takes precedence over `doc_sample_size`: enough
    documents are sampled to reach it (count / questions_per_doc, rounded up)
    and creation stops at `count` total questions."""
    qs = await db.get(QuestionSet, question_set_id)
    if not qs:
        raise ValueError(f"Question set not found: {question_set_id}")
    if count is not None:
        doc_sample_size = max(1, math.ceil(count / max(1, questions_per_doc)))
    docs = await sample_documents(db, qs.library_id, doc_sample_size)
    if not docs:
        logger.warning("Question generation: library has no documents with text",
                       library_id=qs.library_id)
        return 0
    system_prompt = await _get_generation_prompt(db, questions_per_doc)
    svc = QuestionSetService(db)
    created = 0
    for doc in docs:
        if count is not None and created >= count:
            break
        doc_text = (doc.full_text or "")[:MAX_DOC_CHARS]
        header = f"Document title: {doc.title or doc.document_id}\n\n"
        try:
            raw = await _call_generation_llm(db, system_prompt, header + doc_text)
        except Exception as e:
            logger.warning("Question generation: LLM call failed for doc",
                           document_id=doc.id, error=str(e))
            continue
        for item in parse_generated_questions(raw):
            if count is not None and created >= count:
                break
            await svc.add_question(
                question_set_id=question_set_id,
                question_text=item["question"],
                expected_criteria=item["expected_criteria"] or None,
                expected_document_ids=[doc.id],
                origin="generated",
            )
            created += 1
    logger.info("Question generation complete", question_set_id=question_set_id,
                created=created, docs_sampled=len(docs))
    return created
