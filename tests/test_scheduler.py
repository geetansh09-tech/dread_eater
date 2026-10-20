"""
Tests for the energy-aware one-step-per-day scheduler.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.scheduler import (
    ENERGY_FACTORS,
    MAX_DURATION_SLEEPY,
    pick_step_for_today,
)

# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

STEPS = [
    {
        "id": "s-dentist",
        "task_id": "t-1",
        "description": "Open the letter",
        "order_idx": 0,
        "duration_min": 2,
        "status": "pending",
        "snoozed_until": None,
        "dread_score": 7,
        "task_raw_text": "Reply to dentist letter",
    },
    {
        "id": "s-expenses",
        "task_id": "t-2",
        "description": "Open the spreadsheet",
        "order_idx": 0,
        "duration_min": 5,
        "status": "pending",
        "snoozed_until": None,
        "dread_score": 4,
        "task_raw_text": "File expenses",
    },
    {
        "id": "s-report",
        "task_id": "t-3",
        "description": "Read the full report",
        "order_idx": 0,
        "duration_min": 10,
        "status": "pending",
        "snoozed_until": None,
        "dread_score": 3,
        "task_raw_text": "Read quarterly report",
    },
]

_PATCH_PENDING = "backend.scheduler.db.get_all_pending_steps"
_PATCH_REACTIVATE = "backend.scheduler.db.unsnoozed_steps_reactivate"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestScheduler:
    @pytest.mark.asyncio
    async def test_sleepy_only_gets_tiny_steps(self):
        with (
            patch(_PATCH_PENDING, new=AsyncMock(return_value=STEPS)),
            patch(_PATCH_REACTIVATE, new=AsyncMock()),
        ):
            result = await pick_step_for_today("sleepy")

        assert result is not None
        assert result["duration_min"] <= MAX_DURATION_SLEEPY

    @pytest.mark.asyncio
    async def test_awake_can_surface_longer_steps(self):
        with (
            patch(_PATCH_PENDING, new=AsyncMock(return_value=STEPS)),
            patch(_PATCH_REACTIVATE, new=AsyncMock()),
        ):
            result = await pick_step_for_today("awake")

        assert result is not None
        # No duration constraint on awake days

    @pytest.mark.asyncio
    async def test_only_first_pending_step_per_task_is_candidate(self):
        """Three steps from the same task — only order_idx=0 should win."""
        same_task = [
            {**STEPS[0], "id": "s1", "order_idx": 0},
            {**STEPS[0], "id": "s2", "order_idx": 1},
            {**STEPS[0], "id": "s3", "order_idx": 2},
        ]
        with (
            patch(_PATCH_PENDING, new=AsyncMock(return_value=same_task)),
            patch(_PATCH_REACTIVATE, new=AsyncMock()),
        ):
            result = await pick_step_for_today("okay")

        assert result is not None
        assert result["id"] == "s1"

    @pytest.mark.asyncio
    async def test_no_steps_returns_none(self):
        with (
            patch(_PATCH_PENDING, new=AsyncMock(return_value=[])),
            patch(_PATCH_REACTIVATE, new=AsyncMock()),
        ):
            result = await pick_step_for_today("okay")

        assert result is None

    @pytest.mark.asyncio
    async def test_energy_factors_ordered(self):
        assert ENERGY_FACTORS["sleepy"] < ENERGY_FACTORS["okay"] < ENERGY_FACTORS["awake"]

    @pytest.mark.asyncio
    async def test_sleepy_prefers_low_dread_among_tiny_steps(self):
        tiny_steps = [
            {**STEPS[0], "id": "high", "dread_score": 9, "duration_min": 2, "task_id": "t-a"},
            {**STEPS[1], "id": "low",  "dread_score": 2, "duration_min": 2, "task_id": "t-b"},
        ]
        with (
            patch(_PATCH_PENDING, new=AsyncMock(return_value=tiny_steps)),
            patch(_PATCH_REACTIVATE, new=AsyncMock()),
        ):
            result = await pick_step_for_today("sleepy")

        assert result is not None
        assert result["id"] == "low"

    @pytest.mark.asyncio
    async def test_sleepy_fallback_to_shortest_if_none_tiny(self):
        """No steps <= 2 min on sleepy day → fall back to shortest available."""
        big_steps = [
            {**STEPS[0], "id": "b1", "duration_min": 10, "task_id": "t-x"},
            {**STEPS[1], "id": "b2", "duration_min": 5,  "task_id": "t-y"},
        ]
        with (
            patch(_PATCH_PENDING, new=AsyncMock(return_value=big_steps)),
            patch(_PATCH_REACTIVATE, new=AsyncMock()),
        ):
            result = await pick_step_for_today("sleepy")

        assert result is not None
        assert result["id"] == "b2"  # shortest
