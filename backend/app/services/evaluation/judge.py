"""LLM judge for answer-quality scoring (design doc §4).

Model resolution mirrors generation.py: global ModelAssignment for task type
'answer_evaluation', falling back to the onboard default. Judge prompt is the
'answer_evaluation' Prompt Studio task type."""
import json
import re
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models import Prompt

logger = structlog.get_logger()

JUDGE_DEFAULT_PROVIDER = "ollama"
JUDGE_DEFAULT_MODEL = "gemma4:26b-mlx"
JUDGE_TEMPERATURE = 0.1
JUDGE_MAX_TOKENS = 800

JUDGE_FALLBACK_PROMPT = """You are an impartial evaluator grading an AI assistant's answer.

Grade on three dimensions, each 0.0-1.0:
- relevance: does the answer address the question asked?
- accuracy: are the facts correct per the expected criteria?
- groundedness: does the answer stick to retrievable facts (no invention)?

passed = true only if the answer satisfies the expected criteria.

Respond with ONLY a JSON object:
{"relevance": <0-1>, "accuracy": <0-1>, "groundedness": <0-1>, "passed": <bool>, "rationale": "<one or two sentences>"}"""


def _clamp(v) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


def _parse_passed(value) -> bool:
    """LLMs often emit "passed": "false" as a string — bool("false") is True,
    so string values need explicit handling."""
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    return bool(value)


def parse_judge_response(raw: str) -> Optional[dict]:
    """Parse judge output into {scores, passed, rationale}; None if unparseable."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Tolerate conversational preamble/postamble around the JSON object
        brace = re.search(r"(\{.*\})", text, re.DOTALL)
        if not brace:
            logger.warning("Judge: unparseable response", head=text[:120])
            return None
        try:
            data = json.loads(brace.group(1))
        except json.JSONDecodeError:
            logger.warning("Judge: unparseable response", head=text[:120])
            return None
    if not isinstance(data, dict):
        return None
    return {
        "scores": {k: _clamp(data.get(k)) for k in ("relevance", "accuracy", "groundedness")},
        "passed": _parse_passed(data.get("passed", False)),
        "rationale": str(data.get("rationale") or ""),
    }


async def _resolve_judge_model(db: AsyncSession) -> tuple[str, str]:
    from app.models import ModelAssignment
    stmt = select(ModelAssignment).where(
        ModelAssignment.project_id.is_(None),
        ModelAssignment.task_type == "answer_evaluation",
    )
    assignment = (await db.execute(stmt)).scalars().first()
    if assignment:
        return assignment.provider, assignment.model
    return JUDGE_DEFAULT_PROVIDER, JUDGE_DEFAULT_MODEL


async def _get_judge_prompt(db: AsyncSession) -> str:
    stmt = select(Prompt).where(Prompt.task_type == "answer_evaluation",
                                Prompt.is_default == True)  # noqa: E712
    prompt = (await db.execute(stmt)).scalars().first()
    return prompt.system_prompt if prompt else JUDGE_FALLBACK_PROMPT


async def _call_judge_llm(db: AsyncSession, system_prompt: str, user_content: str) -> str:
    """Separate for test mocking. Same provider invocation as generation.py —
    system instructions via the system_prompt kwarg (Anthropic compatibility)."""
    from app.providers.registry import get_registry
    from app.providers.base import ChatMessage, MessageRole

    provider_name, model = await _resolve_judge_model(db)
    registry = get_registry()
    response = await registry.chat(
        provider_name=provider_name,
        model=model,
        messages=[ChatMessage(role=MessageRole.USER, content=user_content)],
        temperature=JUDGE_TEMPERATURE,
        max_tokens=JUDGE_MAX_TOKENS,
        system_prompt=system_prompt,
    )
    return response.content


async def judge_answer(db: AsyncSession, question_text: str,
                       expected_criteria: Optional[str],
                       answer_text: str) -> Optional[dict]:
    """Judge one answer. Returns {scores, passed, rationale} or None on
    unparseable output. Raises on LLM transport errors (caller degrades the
    run to 'partial')."""
    system_prompt = await _get_judge_prompt(db)
    user_content = (
        f"## Question\n{question_text}\n\n"
        f"## Expected criteria\n{expected_criteria or '(none stated — judge on relevance and groundedness)'}\n\n"
        f"## Answer to grade\n{answer_text}"
    )
    raw = await _call_judge_llm(db, system_prompt, user_content)
    return parse_judge_response(raw)
