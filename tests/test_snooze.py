"""
Tests for snooze logic: no streak penalty, future gating, re-activation.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend import database as db


@pytest.fixture
async def temp_db(tmp_path):
    old = db.DB_PATH
    db.DB_PATH = str(tmp_path / "snooze_test.db")
    await db.init_db()
    yield
    db.DB_PATH = old


async def _make_step(tmp_path_unused=None) -> str:
    """Helper: create a task + first step, return the step ID."""
    task_id = await db.create_task(
        raw_text="Test task",
        context_text=None,
        dread_score=5,
        dread_reason="boring",
        first_step="Open document",
        ladder=[],
        prepared_artifacts=[],
        is_mlf=False,
    )
    step_ids = await db.create_steps_for_task(task_id, "Open document", 2, [])
    return step_ids[0]


class TestSnooze:
    @pytest.mark.asyncio
    async def test_snooze_sets_future_date(self, temp_db):
        step_id = await _make_step()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        ok = await db.snooze_step(step_id, tomorrow)
        assert ok
        step = await db.get_step(step_id)
        assert step["status"] == "snoozed"
        assert step["snoozed_until"] == tomorrow

    @pytest.mark.asyncio
    async def test_snoozed_step_not_in_pending_before_date(self, temp_db):
        step_id = await _make_step()
        future = (date.today() + timedelta(days=7)).isoformat()
        await db.snooze_step(step_id, future)
        pending = await db.get_all_pending_steps()
        assert step_id not in [s["id"] for s in pending]

    @pytest.mark.asyncio
    async def test_snoozed_step_reactivates_after_date(self, temp_db):
        step_id = await _make_step()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        await db.snooze_step(step_id, yesterday)
        await db.unsnoozed_steps_reactivate()
        step = await db.get_step(step_id)
        assert step["status"] == "pending"
        assert step["snoozed_until"] is None

    @pytest.mark.asyncio
    async def test_snooze_does_not_create_streak_fields(self, temp_db):
        step_id = await _make_step()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        await db.snooze_step(step_id, tomorrow)
        step = await db.get_step(step_id)
        # No streak or penalty fields should exist
        assert "streak" not in step
        assert "penalty" not in step
        assert step["completed_at"] is None

    @pytest.mark.asyncio
    async def test_multiple_snooze_cycles_work(self, temp_db):
        step_id = await _make_step()
        for extra_days in (1, 2, 3):
            future = (date.today() + timedelta(days=extra_days)).isoformat()
            ok = await db.snooze_step(step_id, future)
            assert ok
        step = await db.get_step(step_id)
        assert step["status"] == "snoozed"
