"""
Dread Eater — Night Runner
==========================
Run while you sleep to pre-write artifact drafts for all tasks that need them.

Usage:
    python -m backend.night_runner

Offline behaviour:
    If Ollama is unreachable, exits cleanly (code 0), writes one line to the
    log, and stores a gentle note that the morning UI will surface with a
    "Retry" button.  No errors, no drama.

Log file: ~/.dread_eater/night.log
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime

from backend.paths import data_dir, db_path, load_config

LOG_DIR = data_dir()
LOG_FILE = LOG_DIR / "night.log"

_OFFLINE_NOTE = (
    "Slothy tried to work overnight but Ollama was napping too. "
    "Tap 'Retry Drafts' and your artifacts will be ready in moments! 🦥"
)


def _setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(LOG_FILE),
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def _load_config() -> dict:
    return load_config()


async def _run() -> None:
    _setup_logging()

    # Import here so DB_PATH can be set from config before first use
    from backend import database as db
    from backend.ollama_client import (
        analyze_task,
        check_ollama_alive,
    )

    cfg = _load_config()
    db.DB_PATH = db_path(cfg)
    base_url: str = cfg["ollama"]["base_url"]
    model: str = cfg["ollama"]["model"]
    system_prompt: str = cfg.get("system_prompt", "")

    await db.init_db()

    # ------------------------------------------------------------------ #
    # Ollama liveness check
    # ------------------------------------------------------------------ #
    alive = await check_ollama_alive(base_url)
    if not alive:
        msg = (
            f"[{datetime.now().isoformat(timespec='seconds')}] "
            "Ollama offline — night run skipped gracefully."
        )
        logging.info("Ollama offline — skipping night run gracefully.")
        print(msg)
        await db.set_config_value("night_runner_offline_note", _OFFLINE_NOTE)
        sys.exit(0)

    # Clear any stale offline note
    await db.set_config_value("night_runner_offline_note", "")

    # ------------------------------------------------------------------ #
    # Process tasks with missing artifacts
    # ------------------------------------------------------------------ #
    tasks = await db.get_tasks_with_stale_artifacts()
    if not tasks:
        logging.info("Night run: all tasks have fresh artifacts — nothing to do.")
        print("🦥 All artifacts are fresh. Sweet dreams!")
        sys.exit(0)

    logging.info("Night run: processing %d task(s) with stale artifacts.", len(tasks))

    succeeded = 0
    for task in tasks:
        tid = task["id"]
        try:
            analysis = await analyze_task(
                raw_text=task["raw_text"],
                context_text=task.get("context_text"),
                model=model,
                system_prompt=system_prompt,
                base_url=base_url,
            )
            if analysis.prepared_artifacts:
                artifacts = [a.model_dump() for a in analysis.prepared_artifacts]
                await db.update_task_artifacts(tid, artifacts)
                logging.info(
                    "Task %s: wrote %d artifact(s).", tid, len(artifacts)
                )
                succeeded += 1
            else:
                logging.warning("Task %s: model returned no artifacts.", tid)
        except Exception as exc:
            logging.error("Task %s: error — %s", tid, exc)

    logging.info(
        "Night run complete. %d/%d tasks updated.", succeeded, len(tasks)
    )
    print(
        f"🦥 Night run done! {succeeded}/{len(tasks)} tasks got fresh drafts. "
        "Sweet dreams!"
    )
    sys.exit(0)


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
