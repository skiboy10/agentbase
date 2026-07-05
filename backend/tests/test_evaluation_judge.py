"""Tests for the LLM answer judge."""
import json
import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.evaluation.judge import (
    parse_judge_response, judge_answer, JUDGE_DEFAULT_MODEL,
)


class TestParsing:
    def test_parse_valid(self):
        raw = json.dumps({"relevance": 0.9, "accuracy": 0.7, "groundedness": 1.0,
                          "passed": True, "rationale": "Covers all criteria."})
        out = parse_judge_response(raw)
        assert out["scores"] == {"relevance": 0.9, "accuracy": 0.7, "groundedness": 1.0}
        assert out["passed"] is True
        assert out["rationale"] == "Covers all criteria."

    def test_parse_clamps_out_of_range(self):
        raw = json.dumps({"relevance": 1.7, "accuracy": -0.2, "groundedness": 0.5,
                          "passed": False, "rationale": "x"})
        out = parse_judge_response(raw)
        assert out["scores"]["relevance"] == 1.0
        assert out["scores"]["accuracy"] == 0.0

    def test_parse_code_fence(self):
        raw = '```json\n{"relevance":1,"accuracy":1,"groundedness":1,"passed":true,"rationale":"ok"}\n```'
        assert parse_judge_response(raw)["passed"] is True

    def test_parse_garbage_returns_none(self):
        assert parse_judge_response("the model rambled") is None


class TestJudgeAnswer:
    async def test_judge_answer_invokes_llm_and_parses(self, db_session: AsyncSession):
        fake = json.dumps({"relevance": 0.8, "accuracy": 0.9, "groundedness": 0.7,
                           "passed": True, "rationale": "good"})
        with patch("app.services.evaluation.judge._call_judge_llm",
                   new=AsyncMock(return_value=fake)) as mock_llm:
            out = await judge_answer(
                db_session,
                question_text="What is ACME onboarding?",
                expected_criteria="Mentions three stages",
                answer_text="ACME onboarding has three stages: ...",
            )
        assert out["passed"] is True
        assert out["scores"]["accuracy"] == 0.9
        prompt_arg = mock_llm.call_args.args[2]  # user content
        assert "three stages" in prompt_arg  # criteria embedded

    async def test_judge_unparseable_returns_none(self, db_session: AsyncSession):
        with patch("app.services.evaluation.judge._call_judge_llm",
                   new=AsyncMock(return_value="not json")):
            assert await judge_answer(db_session, "q", "c", "a") is None


class TestReviewFixes:
    def test_string_false_is_not_passed(self):
        """bool("false") is True in Python — string booleans from LLMs must
        parse correctly."""
        import json
        raw = json.dumps({"relevance": 0.5, "accuracy": 0.5, "groundedness": 0.5,
                          "passed": "false", "rationale": "x"})
        assert parse_judge_response(raw)["passed"] is False

    def test_string_true_is_passed(self):
        import json
        raw = json.dumps({"relevance": 1, "accuracy": 1, "groundedness": 1,
                          "passed": "true", "rationale": "x"})
        assert parse_judge_response(raw)["passed"] is True

    def test_json_with_conversational_preamble(self):
        raw = ('Sure! Here is my evaluation:\n'
               '{"relevance": 0.9, "accuracy": 0.8, "groundedness": 0.7, '
               '"passed": true, "rationale": "ok"} Hope that helps!')
        out = parse_judge_response(raw)
        assert out is not None
        assert out["scores"]["relevance"] == 0.9
