"""
Tests for shrink-step: AI splitting, DB mechanics, undo, one-step-at-a-time.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from backend import database as db
from backend.ollama_client import shrink_step_with_ai


@pytest.fixture
async def temp_db(tmp_path):
    old = db.DB_PATH
    db.DB_PATH = str(tmp_path / "shrink_test.db")
    await db.init_db()
    yield
    db.DB_PATH = old


async def _make_task_and_step(description: str = "Big step") -> tuple[str, str]:
    task_id = await db.create_task(
        raw_text="Big task",
        context_text=None,
        dread_score=6,
        dread_reason="overwhelming",
        first_step=description,
        ladder=[],
        prepared_artifacts=[],
        is_mlf=False,
    )
    step_ids = await db.create_steps_for_task(task_id, description, 10, [])
    return task_id, step_ids[0]


class TestShrinkStepAI:
    @pytest.mark.asyncio
    async def test_returns_at_least_two_steps(self):
        payload = json.dumps({"steps": [
            {"description": "a", "duration_min": 2},
            {"description": "b", "duration_min": 3},
        ]})
        with patch("backend.ollama_client._generate", new=AsyncMock(return_value=payload)):
            result = await shrink_step_with_ai("File my expenses")
        assert len(result) >= 2

    @pytest.mark.asyncio
    async def test_each_step_under_5_min(self):
        payload = json.dumps({"steps": [
            {"description": "a", "duration_min": 3},
            {"description": "b", "duration_min": 4},
            {"description": "c", "duration_min": 5},
        ]})
        with patch("backend.ollama_client._generate", new=AsyncMock(return_value=payload)):
            result = await shrink_step_with_ai("Write the report")
        for step in result:
            assert step["duration_min"] <= 5

    @pytest.mark.asyncio
    async def test_fallback_on_bad_json(self):
        with patch("backend.ollama_client._generate", new=AsyncMock(return_value="not json")):
            result = await shrink_step_with_ai("Do the thing")
        assert len(result) >= 2
        for step in result:
            assert "description" in step
            assert "duration_min" in step

    @pytest.mark.asyncio
    async def test_model_over_4_steps_capped_at_4(self):
        payload = json.dumps({"steps": [
            {"description": f"step {i}", "duration_min": 2} for i in range(8)
        ]})
        with patch("backend.ollama_client._generate", new=AsyncMock(return_value=payload)):
            result = await shrink_step_with_ai("Very big task")
        assert len(result) <= 4


class TestShrinkStepDB:
    @pytest.mark.asyncio
    async def test_original_step_marked_shrunk(self, temp_db):
        _, step_id = await _make_task_and_step()
        new = [{"description": "Tiny 1", "duration_min": 2},
               {"description": "Tiny 2", "duration_min": 2}]
        await db.shrink_step(step_id, new)
        original = await db.get_step(step_id)
        assert original["status"] == "shrunk"

    @pytest.mark.asyncio
    async def test_new_steps_reference_original(self, temp_db):
        _, step_id = await _make_task_and_step()
        new = [{"description": "Mini 1", "duration_min": 2},
               {"description": "Mini 2", "duration_min": 2}]
        first_id, rest_ids = await db.shrink_step(step_id, new)
        first = await db.get_step(first_id)
        assert first["shrunk_from"] == step_id
        assert bool(first["is_shrunken"])
        for rid in rest_ids:
            s = await db.get_step(rid)
            assert s["shrunk_from"] == step_id

    @pytest.mark.asyncio
    async def test_undo_shrink_restores_original(self, temp_db):
        _, step_id = await _make_task_and_step()
        new = [{"description": "Sub 1", "duration_min": 2},
               {"description": "Sub 2", "duration_min": 2}]
        await db.shrink_step(step_id, new)
        ok = await db.undo_shrink(step_id)
        assert ok
        original = await db.get_step(step_id)
        assert original["status"] == "pending"

    @pytest.mark.asyncio
    async def test_undo_removes_shrunken_children(self, temp_db):
        _, step_id = await _make_task_and_step()
        new = [{"description": "Sub 1", "duration_min": 2},
               {"description": "Sub 2", "duration_min": 2}]
        first_id, rest_ids = await db.shrink_step(step_id, new)
        await db.undo_shrink(step_id)
        # Children should be gone
        assert await db.get_step(first_id) is None
        for rid in rest_ids:
            assert await db.get_step(rid) is None

    @pytest.mark.asyncio
    async def test_first_shrunken_step_surfaced_first(self, temp_db):
        task_id, step_id = await _make_task_and_step()
        new = [
            {"description": "First tiny",  "duration_min": 2},
            {"description": "Second tiny", "duration_min": 2},
            {"description": "Third tiny",  "duration_min": 2},
        ]
        first_id, _ = await db.shrink_step(step_id, new)
        pending = await db.get_pending_steps_for_task(task_id)
        assert pending[0]["id"] == first_id
