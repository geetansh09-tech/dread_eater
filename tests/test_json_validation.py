"""
Test JSON parsing pipeline: extraction, Pydantic validation, retry, fallback.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.models import LLMAnalysis
from backend.ollama_client import FALLBACK_ANALYSIS, _extract_json, analyze_task
from backend.security import strip_think_blocks


# ---------------------------------------------------------------------------
# _extract_json
# ---------------------------------------------------------------------------

class TestExtractJson:
    def test_valid_direct_json(self):
        text = '{"dread_score": 7, "dread_reason": "test"}'
        result = _extract_json(text)
        assert result == {"dread_score": 7, "dread_reason": "test"}

    def test_json_in_code_block(self):
        text = '```json\n{"dread_score": 5}\n```'
        result = _extract_json(text)
        assert result == {"dread_score": 5}

    def test_json_embedded_in_prose(self):
        text = 'Here is the output: {"dread_score": 3, "dread_reason": "boring"} Done.'
        result = _extract_json(text)
        assert result is not None
        assert result["dread_score"] == 3

    def test_plain_text_returns_none(self):
        assert _extract_json("This is plain text.") is None

    def test_malformed_json_returns_none(self):
        assert _extract_json('{"key": missing_quote}') is None

    def test_empty_string_returns_none(self):
        assert _extract_json("") is None

    def test_code_block_no_lang_tag(self):
        text = '```\n{"dread_score": 9}\n```'
        result = _extract_json(text)
        assert result is not None
        assert result["dread_score"] == 9


# ---------------------------------------------------------------------------
# strip_think_blocks
# ---------------------------------------------------------------------------

class TestStripThinkBlocks:
    def test_strips_think_block(self):
        raw = "<think>reasoning here</think>\nHello!"
        assert strip_think_blocks(raw) == "Hello!"

    def test_strips_multiline_think(self):
        raw = "<think>\nline1\nline2\n</think>\nJSON"
        assert strip_think_blocks(raw) == "JSON"

    def test_no_think_block_unchanged(self):
        raw = "plain text"
        assert strip_think_blocks(raw) == "plain text"

    def test_case_insensitive(self):
        raw = "<THINK>stuff</THINK> result"
        assert strip_think_blocks(raw) == "result"


# ---------------------------------------------------------------------------
# analyze_task — full pipeline
# ---------------------------------------------------------------------------

_VALID_PAYLOAD = {
    "dread_score": 8,
    "dread_reason": "Awkward conversation",
    "first_step": "Write down what I want to say",
    "first_step_duration_min": 2,
    "ladder": [{"description": "Practice", "duration_min": 5}],
    "prepared_artifacts": [],
    "is_medical_legal_financial": False,
    "mascot_message": "Sloths don't rush, and neither do you!",
}


class TestAnalyzeTask:
    @pytest.mark.asyncio
    async def test_valid_response_parsed(self):
        with patch(
            "backend.ollama_client._generate",
            new=AsyncMock(return_value=json.dumps(_VALID_PAYLOAD)),
        ):
            result = await analyze_task("I need to give feedback to a colleague")
        assert isinstance(result, LLMAnalysis)
        assert result.dread_score == 8

    @pytest.mark.asyncio
    async def test_think_block_stripped_before_parse(self):
        payload_with_think = (
            "<think>Let me think carefully...</think>\n" + json.dumps(_VALID_PAYLOAD)
        )
        with patch(
            "backend.ollama_client._generate",
            new=AsyncMock(return_value=payload_with_think),
        ):
            result = await analyze_task("Any task")
        assert result.dread_score == 8  # parsed correctly after stripping

    @pytest.mark.asyncio
    async def test_both_attempts_fail_returns_fallback(self):
        with patch(
            "backend.ollama_client._generate",
            new=AsyncMock(return_value="not json at all !!!!"),
        ):
            result = await analyze_task("Some task")
        assert result is FALLBACK_ANALYSIS

    @pytest.mark.asyncio
    async def test_retry_on_first_failure(self):
        """First call → bad JSON; second call → valid JSON.  Should succeed."""
        call_count = 0

        async def _mock(*_args, **_kwargs) -> str:
            nonlocal call_count
            call_count += 1
            return "{{{{ invalid" if call_count == 1 else json.dumps(_VALID_PAYLOAD)

        with patch("backend.ollama_client._generate", new=_mock):
            result = await analyze_task("Some task")

        assert result.dread_score == 8
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_exception_on_first_attempt_retries(self):
        call_count = 0

        async def _mock(*_args, **_kwargs) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Ollama blipped")
            return json.dumps(_VALID_PAYLOAD)

        with patch("backend.ollama_client._generate", new=_mock):
            result = await analyze_task("Some task")

        assert result.dread_score == 8
        assert call_count == 2


# ---------------------------------------------------------------------------
# LLMAnalysis model validation
# ---------------------------------------------------------------------------

class TestLLMAnalysisModel:
    def test_dread_score_too_high_raises(self):
        with pytest.raises(Exception):
            LLMAnalysis(
                dread_score=15,
                dread_reason="x",
                first_step="x",
                ladder=[],
                prepared_artifacts=[],
                mascot_message="x",
            )

    def test_dread_score_too_low_raises(self):
        with pytest.raises(Exception):
            LLMAnalysis(
                dread_score=0,
                dread_reason="x",
                first_step="x",
                ladder=[],
                prepared_artifacts=[],
                mascot_message="x",
            )

    def test_ladder_capped_at_6(self):
        many = [{"description": f"Step {i}", "duration_min": 5} for i in range(10)]
        analysis = LLMAnalysis(
            dread_score=5,
            dread_reason="test",
            first_step="start",
            ladder=many,
            prepared_artifacts=[],
            mascot_message="hi",
        )
        assert len(analysis.ladder) <= 6

    def test_ladder_duration_capped_at_10(self):
        steps = [{"description": "Big step", "duration_min": 999}]
        analysis = LLMAnalysis(
            dread_score=5,
            dread_reason="test",
            first_step="start",
            ladder=steps,
            prepared_artifacts=[],
            mascot_message="hi",
        )
        assert analysis.ladder[0]["duration_min"] <= 10
