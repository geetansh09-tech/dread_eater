"""
SQLite database layer using aiosqlite.

All queries use parameterised statements — never f-string SQL.
"""
from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import aiosqlite

# Overrideable by main.py after reading config
DB_PATH: str = "./dread_eater.db"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.utcnow().isoformat()


def _today() -> str:
    return date.today().isoformat()


@asynccontextmanager
async def _get_db():
    """Open a connection; compatible with all aiosqlite versions."""
    db = await aiosqlite.connect(DB_PATH)
    try:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        yield db
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

async def init_db() -> None:
    async with _get_db() as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id                          TEXT PRIMARY KEY,
                raw_text                    TEXT NOT NULL,
                context_text                TEXT,
                dread_score                 INTEGER NOT NULL DEFAULT 5,
                dread_reason                TEXT,
                first_step                  TEXT,
                ladder                      TEXT NOT NULL DEFAULT '[]',
                prepared_artifacts          TEXT NOT NULL DEFAULT '[]',
                is_medical_legal_financial  INTEGER NOT NULL DEFAULT 0,
                created_at                  TEXT NOT NULL,
                updated_at                  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS steps (
                id           TEXT PRIMARY KEY,
                task_id      TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                description  TEXT NOT NULL,
                order_idx    INTEGER NOT NULL DEFAULT 0,
                duration_min INTEGER NOT NULL DEFAULT 5,
                status       TEXT NOT NULL DEFAULT 'pending',
                snoozed_until TEXT,
                completed_at TEXT,
                is_shrunken  INTEGER NOT NULL DEFAULT 0,
                shrunk_from  TEXT,
                mascot_message TEXT,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS daily_logs (
                id               TEXT PRIMARY KEY,
                date             TEXT NOT NULL UNIQUE,
                energy_level     TEXT NOT NULL DEFAULT 'okay',
                surfaced_step_id TEXT REFERENCES steps(id),
                created_at       TEXT NOT NULL,
                updated_at       TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS config (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_steps_task_id ON steps(task_id);
            CREATE INDEX IF NOT EXISTS idx_steps_status  ON steps(status);
            CREATE INDEX IF NOT EXISTS idx_daily_date    ON daily_logs(date);
        """)
        await db.commit()


# ---------------------------------------------------------------------------
# Task CRUD
# ---------------------------------------------------------------------------

async def create_task(
    raw_text: str,
    context_text: Optional[str],
    dread_score: int,
    dread_reason: str,
    first_step: str,
    ladder: list,
    prepared_artifacts: list,
    is_mlf: bool,
) -> str:
    task_id = str(uuid.uuid4())
    now = _now()
    async with _get_db() as db:
        await db.execute(
            """
            INSERT INTO tasks
                (id, raw_text, context_text, dread_score, dread_reason,
                 first_step, ladder, prepared_artifacts,
                 is_medical_legal_financial, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                task_id, raw_text, context_text, dread_score, dread_reason,
                first_step, json.dumps(ladder), json.dumps(prepared_artifacts),
                int(is_mlf), now, now,
            ),
        )
        await db.commit()
    return task_id


async def create_steps_for_task(
    task_id: str,
    first_step: str,
    first_step_duration: int,
    ladder: list,
) -> List[str]:
    """Create the first step + ladder steps. Returns list of step IDs in order."""
    now = _now()
    step_ids: List[str] = []

    async with _get_db() as db:
        # First (tiny) step
        sid = str(uuid.uuid4())
        step_ids.append(sid)
        await db.execute(
            """
            INSERT INTO steps
                (id, task_id, description, order_idx, duration_min,
                 status, created_at, updated_at)
            VALUES (?,?,?,0,?,'pending',?,?)
            """,
            (sid, task_id, first_step, first_step_duration, now, now),
        )

        # Ladder steps
        for i, step in enumerate(ladder):
            sid = str(uuid.uuid4())
            step_ids.append(sid)
            await db.execute(
                """
                INSERT INTO steps
                    (id, task_id, description, order_idx, duration_min,
                     status, created_at, updated_at)
                VALUES (?,?,?,?,?,'pending',?,?)
                """,
                (
                    sid, task_id, step["description"],
                    i + 1, step.get("duration_min", 5),
                    now, now,
                ),
            )

        await db.commit()
    return step_ids


async def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    async with _get_db() as db:
        cur = await db.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_all_tasks() -> List[Dict[str, Any]]:
    async with _get_db() as db:
        cur = await db.execute("SELECT * FROM tasks ORDER BY created_at DESC")
        return [dict(r) for r in await cur.fetchall()]


async def delete_task(task_id: str) -> bool:
    async with _get_db() as db:
        cur = await db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        await db.commit()
        return cur.rowcount > 0


async def update_task_artifacts(task_id: str, artifacts: list) -> None:
    async with _get_db() as db:
        await db.execute(
            "UPDATE tasks SET prepared_artifacts=?, updated_at=? WHERE id=?",
            (json.dumps(artifacts), _now(), task_id),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Steps CRUD
# ---------------------------------------------------------------------------

async def get_step(step_id: str) -> Optional[Dict[str, Any]]:
    async with _get_db() as db:
        cur = await db.execute(
            """
            SELECT s.*, t.raw_text AS task_raw_text, t.dread_score
            FROM steps s
            JOIN tasks t ON s.task_id = t.id
            WHERE s.id=?
            """,
            (step_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_pending_steps_for_task(task_id: str) -> List[Dict[str, Any]]:
    async with _get_db() as db:
        cur = await db.execute(
            """
            SELECT * FROM steps
            WHERE task_id=? AND status='pending'
            ORDER BY order_idx ASC
            """,
            (task_id,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_all_pending_steps() -> List[Dict[str, Any]]:
    """All pending steps joined with task dread_score, excluding still-snoozed."""
    today = _today()
    async with _get_db() as db:
        cur = await db.execute(
            """
            SELECT s.*, t.raw_text AS task_raw_text, t.dread_score
            FROM steps s
            JOIN tasks t ON s.task_id = t.id
            WHERE s.status = 'pending'
              AND (s.snoozed_until IS NULL OR s.snoozed_until <= ?)
            ORDER BY s.task_id, s.order_idx ASC
            """,
            (today,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def mark_step_done(step_id: str, mascot_message: str = "") -> bool:
    now = _now()
    async with _get_db() as db:
        cur = await db.execute(
            """
            UPDATE steps
            SET status='done', completed_at=?, mascot_message=?, updated_at=?
            WHERE id=? AND status != 'done'
            """,
            (now, mascot_message, now, step_id),
        )
        await db.commit()
        return cur.rowcount > 0


async def snooze_step(
    step_id: str,
    until_date: str,
    mascot_message: str = "",
) -> bool:
    now = _now()
    async with _get_db() as db:
        cur = await db.execute(
            """
            UPDATE steps
            SET status='snoozed', snoozed_until=?, mascot_message=?, updated_at=?
            WHERE id=?
            """,
            (until_date, mascot_message, now, step_id),
        )
        await db.commit()
        return cur.rowcount > 0


async def unsnoozed_steps_reactivate() -> None:
    """Flip snoozed steps back to pending when their date has passed."""
    today = _today()
    async with _get_db() as db:
        await db.execute(
            """
            UPDATE steps
            SET status='pending', snoozed_until=NULL, updated_at=?
            WHERE status='snoozed' AND snoozed_until <= ?
            """,
            (_now(), today),
        )
        await db.commit()


async def shrink_step(
    step_id: str,
    new_steps: list,
) -> Tuple[str, List[str]]:
    """
    Mark the original step as 'shrunk', insert new micro-steps in its place.

    Inline replacement: the new steps occupy the original step's order_idx
    position onward; everything that was after shifts up.

    Returns (first_new_step_id, [remaining_new_step_ids]).
    """
    now = _now()
    original = await get_step(step_id)
    if not original:
        raise ValueError(f"Step {step_id} not found")

    task_id = original["task_id"]
    original_order = original["order_idx"]
    shift = len(new_steps)

    new_step_ids: List[str] = []

    async with _get_db() as db:
        # Mark original as shrunk
        await db.execute(
            "UPDATE steps SET status='shrunk', updated_at=? WHERE id=?",
            (now, step_id),
        )

        # Shift later pending steps to make room
        await db.execute(
            """
            UPDATE steps
            SET order_idx = order_idx + ?, updated_at = ?
            WHERE task_id=? AND status='pending' AND order_idx > ?
            """,
            (shift - 1, now, task_id, original_order),
        )

        # Insert new micro-steps starting at original_order
        for i, ns in enumerate(new_steps):
            sid = str(uuid.uuid4())
            new_step_ids.append(sid)
            await db.execute(
                """
                INSERT INTO steps
                    (id, task_id, description, order_idx, duration_min,
                     status, is_shrunken, shrunk_from, created_at, updated_at)
                VALUES (?,?,?,?,?,'pending',1,?,?,?)
                """,
                (
                    sid, task_id,
                    ns["description"],
                    original_order + i,
                    ns.get("duration_min", 2),
                    step_id, now, now,
                ),
            )

        await db.commit()

    return new_step_ids[0], new_step_ids[1:]


async def undo_shrink(original_step_id: str) -> bool:
    """Restore the original step and delete all shrunken replacements."""
    now = _now()
    async with _get_db() as db:
        cur = await db.execute(
            "SELECT * FROM steps WHERE id=? AND status='shrunk'",
            (original_step_id,),
        )
        original = await cur.fetchone()
        if not original:
            return False

        # Remove shrunken children
        await db.execute(
            "DELETE FROM steps WHERE shrunk_from=? AND is_shrunken=1",
            (original_step_id,),
        )

        # Restore original
        await db.execute(
            "UPDATE steps SET status='pending', updated_at=? WHERE id=?",
            (now, original_step_id),
        )

        await db.commit()
        return True


# ---------------------------------------------------------------------------
# Daily log
# ---------------------------------------------------------------------------

async def get_today_log() -> Optional[Dict[str, Any]]:
    async with _get_db() as db:
        cur = await db.execute(
            "SELECT * FROM daily_logs WHERE date=?", (_today(),)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def set_energy_level(energy_level: str) -> Dict[str, Any]:
    today = _today()
    now = _now()
    async with _get_db() as db:
        cur = await db.execute(
            "SELECT id FROM daily_logs WHERE date=?", (today,)
        )
        row = await cur.fetchone()
        if row:
            await db.execute(
                "UPDATE daily_logs SET energy_level=?, updated_at=? WHERE date=?",
                (energy_level, now, today),
            )
        else:
            await db.execute(
                """
                INSERT INTO daily_logs (id, date, energy_level, created_at, updated_at)
                VALUES (?,?,?,?,?)
                """,
                (str(uuid.uuid4()), today, energy_level, now, now),
            )
        await db.commit()
    log = await get_today_log()
    return log  # type: ignore[return-value]


async def set_surfaced_step(step_id: str) -> None:
    today = _today()
    now = _now()
    async with _get_db() as db:
        # Ensure today's log exists
        cur = await db.execute(
            "SELECT id FROM daily_logs WHERE date=?", (today,)
        )
        if not await cur.fetchone():
            await db.execute(
                """
                INSERT INTO daily_logs (id, date, energy_level, created_at, updated_at)
                VALUES (?,?,'okay',?,?)
                """,
                (str(uuid.uuid4()), today, now, now),
            )
        await db.execute(
            "UPDATE daily_logs SET surfaced_step_id=?, updated_at=? WHERE date=?",
            (step_id, now, today),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Wins
# ---------------------------------------------------------------------------

async def get_wins() -> Tuple[List[Dict[str, Any]], int]:
    """Returns (list_of_win_dicts, fully_finished_task_count)."""
    async with _get_db() as db:
        cur = await db.execute(
            """
            SELECT s.id AS step_id, s.task_id, s.description,
                   s.completed_at, s.mascot_message,
                   t.raw_text AS task_raw_text
            FROM steps s
            JOIN tasks t ON s.task_id = t.id
            WHERE s.status = 'done'
            ORDER BY s.completed_at DESC
            """
        )
        wins = [dict(r) for r in await cur.fetchall()]

        # Tasks where every non-shrunk step is done
        cur2 = await db.execute(
            """
            SELECT COUNT(*) AS cnt FROM tasks t
            WHERE NOT EXISTS (
                SELECT 1 FROM steps s
                WHERE s.task_id = t.id
                  AND s.status NOT IN ('done', 'shrunk')
            )
            AND EXISTS (
                SELECT 1 FROM steps s
                WHERE s.task_id = t.id AND s.status = 'done'
            )
            """
        )
        row = await cur2.fetchone()
        fully_finished = row["cnt"] if row else 0

    return wins, fully_finished


# ---------------------------------------------------------------------------
# Config KV store
# ---------------------------------------------------------------------------

async def get_config_value(key: str, default: str = "") -> str:
    async with _get_db() as db:
        cur = await db.execute(
            "SELECT value FROM config WHERE key=?", (key,)
        )
        row = await cur.fetchone()
        return row["value"] if row else default


async def set_config_value(key: str, value: str) -> None:
    async with _get_db() as db:
        await db.execute(
            """
            INSERT INTO config (key, value) VALUES (?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (key, value),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Export / Wipe
# ---------------------------------------------------------------------------

async def export_all() -> Dict[str, Any]:
    async with _get_db() as db:
        tasks_cur = await db.execute("SELECT * FROM tasks")
        tasks = [dict(r) for r in await tasks_cur.fetchall()]

        steps_cur = await db.execute("SELECT * FROM steps")
        steps = [dict(r) for r in await steps_cur.fetchall()]

        logs_cur = await db.execute("SELECT * FROM daily_logs")
        logs = [dict(r) for r in await logs_cur.fetchall()]

        cfg_cur = await db.execute("SELECT * FROM config")
        cfg = [dict(r) for r in await cfg_cur.fetchall()]

    # Deserialise stored JSON fields
    for t in tasks:
        for field in ("ladder", "prepared_artifacts"):
            if isinstance(t.get(field), str):
                try:
                    t[field] = json.loads(t[field])
                except Exception:
                    t[field] = []

    return {
        "export_version": 1,
        "exported_at": _now(),
        "tasks": tasks,
        "steps": steps,
        "daily_logs": logs,
        "config": cfg,
    }


async def wipe_all() -> None:
    async with _get_db() as db:
        await db.executescript(
            "DELETE FROM steps; DELETE FROM tasks; "
            "DELETE FROM daily_logs; DELETE FROM config;"
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Night-runner helpers
# ---------------------------------------------------------------------------

async def get_tasks_with_stale_artifacts() -> List[Dict[str, Any]]:
    """Tasks where prepared_artifacts is missing or empty."""
    async with _get_db() as db:
        cur = await db.execute(
            """
            SELECT * FROM tasks
            WHERE prepared_artifacts IS NULL
               OR prepared_artifacts = '[]'
               OR prepared_artifacts = ''
            ORDER BY dread_score DESC
            """
        )
        return [dict(r) for r in await cur.fetchall()]


async def count_completed_today() -> int:
    """Number of steps completed today (UTC date, matching stored timestamps)."""
    today = _now()[:10]
    async with _get_db() as db:
        cur = await db.execute(
            "SELECT COUNT(*) AS cnt FROM steps WHERE status='done' AND substr(completed_at,1,10)=?",
            (today,),
        )
        row = await cur.fetchone()
        return int(row["cnt"]) if row else 0
