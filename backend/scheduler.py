"""
Daily task scheduler — picks the one step to show today.

Scoring formula (lower score = better fit):
    score = dread_weight + duration_weight

Where:
    dread_weight    = dread_score    × (1 − energy_factor)
    duration_weight = duration_min   × (1 − energy_factor) × 0.5

energy_factor: sleepy=0.3, okay=0.6, awake=1.0

On Sleepy days, steps with duration_min > MAX_DURATION_SLEEPY are excluded
entirely.  If that filter leaves nothing, fall back to the globally shortest
available step (to always give the user *something*).

Only the first pending step per task is ever considered — this is the
"one step at a time" guarantee.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend import database as db

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ENERGY_FACTORS: Dict[str, float] = {
    "sleepy": 0.3,
    "okay":   0.6,
    "awake":  1.0,
}

MAX_DURATION_SLEEPY: int = 2   # minutes — hard filter on sleepy days


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def pick_step_for_today(energy_level: str = "okay") -> Optional[Dict[str, Any]]:
    """
    Return the single best step for today, or None if nothing is pending.

    Guarantees:
    - Only one step per task is ever a candidate (the lowest order_idx pending step).
    - On sleepy days, only steps ≤ MAX_DURATION_SLEEPY minutes qualify.
    - Returns None when no tasks are pending (not an error — celebrate!).
    """
    # Re-activate any snoozed steps whose date has arrived
    await db.unsnoozed_steps_reactivate()

    all_pending = await db.get_all_pending_steps()
    if not all_pending:
        return None

    factor = ENERGY_FACTORS.get(energy_level, 0.6)

    # --- Step 1: one candidate per task (first pending step in order) ---
    task_first: Dict[str, Dict[str, Any]] = {}
    for step in all_pending:
        tid = step["task_id"]
        if tid not in task_first:
            task_first[tid] = step

    candidates: List[Dict[str, Any]] = list(task_first.values())

    # --- Step 2: energy filter ---
    if energy_level == "sleepy":
        tiny = [s for s in candidates if s.get("duration_min", 99) <= MAX_DURATION_SLEEPY]
        if tiny:
            candidates = tiny
        else:
            # Nothing tiny → pick the absolute shortest available
            candidates = sorted(candidates, key=lambda s: s.get("duration_min", 99))[:1]

    if not candidates:
        return None

    # --- Step 3: score and pick lowest ---
    def _score(step: Dict[str, Any]) -> float:
        dread = float(step.get("dread_score", 5))
        dur   = float(step.get("duration_min", 5))
        return dread * (1 - factor) + dur * (1 - factor) * 0.5

    candidates.sort(key=_score)
    return candidates[0]
