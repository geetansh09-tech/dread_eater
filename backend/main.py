"""
Dread Eater — FastAPI application entry point.

Binds to 127.0.0.1 only (never 0.0.0.0).
Docs endpoints disabled for security.
"""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend import database as db
from backend.models import (
    ConfigResponse,
    DumpRequest,
    EnergyRequest,
    HealthResponse,
    ShrinkResponse,
    StepResponse,
    TodayResponse,
    UpdateConfigRequest,
    WinEntry,
    WinsResponse,
)
from backend.ollama_client import (
    analyze_task,
    check_ollama_alive,
    generate_mascot_message,
    list_models,
    shrink_step_with_ai,
)
from backend.paths import FRONTEND_DIR, db_path, load_config
from backend.scheduler import pick_step_for_today
from backend.security import (
    BodySizeLimitMiddleware,
    SecurityHeadersMiddleware,
    check_ai_rate_limit,
    detect_mlf,
    sanitize_text,
)
from backend.seed import seed_if_empty

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _load_cfg() -> dict:
    return load_config()


def _cfg_model() -> str:
    return _load_cfg().get("ollama", {}).get("model", "qwen3:4b")


def _cfg_prompt() -> str:
    return _load_cfg().get("system_prompt", "")


def _cfg_base_url() -> str:
    return _load_cfg().get("ollama", {}).get("base_url", "http://localhost:11434")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(app: FastAPI):  # noqa: ARG001
    cfg = _load_cfg()
    db.DB_PATH = db_path(cfg)
    await db.init_db()
    await seed_if_empty()
    yield


app = FastAPI(
    title="Dread Eater",
    description="Local-first procrastination breaker with a sloth mascot",
    lifespan=_lifespan,
    docs_url=None,    # disable Swagger UI
    redoc_url=None,   # disable ReDoc
    openapi_url=None, # disable OpenAPI schema endpoint
)

# Only accept requests from localhost
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["localhost", "127.0.0.1", "::1"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(BodySizeLimitMiddleware)

# Serve static frontend files
_FRONTEND = FRONTEND_DIR
app.mount("/static", StaticFiles(directory=str(_FRONTEND)), name="static")


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

def _row_to_step(row: dict) -> StepResponse:
    return StepResponse(
        id=row["id"],
        task_id=row["task_id"],
        description=row["description"],
        order_idx=row["order_idx"],
        duration_min=row["duration_min"],
        status=row["status"],
        snoozed_until=row.get("snoozed_until"),
        completed_at=row.get("completed_at"),
        is_shrunken=bool(row.get("is_shrunken", 0)),
        shrunk_from=row.get("shrunk_from"),
        task_raw_text=row.get("task_raw_text"),
        mascot_message=row.get("mascot_message"),
    )


async def _effective_model() -> str:
    return await db.get_config_value("model", _cfg_model())


async def _effective_prompt() -> str:
    return await db.get_config_value("system_prompt", _cfg_prompt())


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health", response_model=HealthResponse)
async def health():
    model = await _effective_model()
    base_url = _cfg_base_url()
    alive = await check_ollama_alive(base_url)
    return HealthResponse(
        status="ok",
        model=model,
        ollama_alive=alive,
        db_path=db.DB_PATH,
    )


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@app.get("/api/config", response_model=ConfigResponse)
async def get_config():
    model = await _effective_model()
    prompt = await _effective_prompt()
    models = await list_models(_cfg_base_url())
    # Ensure current model appears first, even if Ollama is offline
    if model and model not in models:
        models = [model] + models
    return ConfigResponse(model=model, system_prompt=prompt, available_models=models)


@app.put("/api/config")
async def update_config(req: UpdateConfigRequest):
    if req.model is not None:
        await db.set_config_value("model", sanitize_text(req.model))
    if req.system_prompt is not None:
        await db.set_config_value("system_prompt", sanitize_text(req.system_prompt))
    return {"status": "updated"}


@app.get("/api/models")
async def get_models():
    return {"models": await list_models(_cfg_base_url())}


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@app.post("/api/tasks")
async def create_task(req: DumpRequest):
    if not check_ai_rate_limit():
        raise HTTPException(429, "Too many AI requests — please wait a moment.")

    raw = sanitize_text(req.raw_text)
    ctx = sanitize_text(req.context_text) if req.context_text else None
    if not raw:
        raise HTTPException(400, "Task text cannot be empty.")

    model = await _effective_model()
    prompt = await _effective_prompt()
    base_url = _cfg_base_url()

    mlf_keyword = detect_mlf(raw) or (ctx and detect_mlf(ctx))

    analysis = await analyze_task(
        raw_text=raw,
        context_text=ctx,
        model=model,
        system_prompt=prompt,
        base_url=base_url,
    )

    is_mlf = analysis.is_medical_legal_financial or bool(mlf_keyword)
    artifacts = [a.model_dump() for a in analysis.prepared_artifacts]

    task_id = await db.create_task(
        raw_text=raw,
        context_text=ctx,
        dread_score=analysis.dread_score,
        dread_reason=analysis.dread_reason,
        first_step=analysis.first_step,
        ladder=analysis.ladder,
        prepared_artifacts=artifacts,
        is_mlf=is_mlf,
    )
    await db.create_steps_for_task(
        task_id=task_id,
        first_step=analysis.first_step,
        first_step_duration=analysis.first_step_duration_min,
        ladder=analysis.ladder,
    )
    task = await db.get_task(task_id)

    return {
        "id": task_id,
        "raw_text": raw,
        "dread_score": analysis.dread_score,
        "dread_reason": analysis.dread_reason,
        "first_step": analysis.first_step,
        "ladder": analysis.ladder,
        "prepared_artifacts": artifacts,
        "is_medical_legal_financial": is_mlf,
        "mascot_message": analysis.mascot_message,
        "created_at": task["created_at"] if task else "",
    }


@app.get("/api/tasks")
async def list_tasks():
    tasks = await db.get_all_tasks()
    for t in tasks:
        for field in ("ladder", "prepared_artifacts"):
            if isinstance(t.get(field), str):
                try:
                    t[field] = json.loads(t[field])
                except Exception:
                    t[field] = []
    return {"tasks": tasks}


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    task = await db.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found.")
    for field in ("ladder", "prepared_artifacts"):
        if isinstance(task.get(field), str):
            try:
                task[field] = json.loads(task[field])
            except Exception:
                task[field] = []
    return task


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str):
    if not await db.delete_task(task_id):
        raise HTTPException(404, "Task not found.")
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Today
# ---------------------------------------------------------------------------

@app.get("/api/today", response_model=TodayResponse)
async def get_today():
    today_log = await db.get_today_log()
    energy = today_log["energy_level"] if today_log else "okay"

    step = await pick_step_for_today(energy)

    tasks = await db.get_all_tasks()
    offline_note = await db.get_config_value("night_runner_offline_note", "")

    if step:
        await db.set_surfaced_step(step["id"])
        model = await _effective_model()
        prompt = await _effective_prompt()
        base_url = _cfg_base_url()
        step["mascot_message"] = await generate_mascot_message(
            f"about to tackle: {step['description']}",
            model=model, system_prompt=prompt, base_url=base_url,
        )

    return TodayResponse(
        step=_row_to_step(step) if step else None,
        energy_level=energy,
        total_tasks=len(tasks),
        completed_today=await db.count_completed_today(),
        ollama_offline_note=offline_note or None,
    )


@app.post("/api/today/energy")
async def set_energy(req: EnergyRequest):
    await db.set_energy_level(req.energy_level.value)
    return {"status": "ok", "energy_level": req.energy_level.value}


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

@app.post("/api/steps/{step_id}/done")
async def mark_done(step_id: str):
    if not check_ai_rate_limit():
        raise HTTPException(429, "Too many requests.")

    step = await db.get_step(step_id)
    if not step:
        raise HTTPException(404, "Step not found.")

    model = await _effective_model()
    prompt = await _effective_prompt()
    base_url = _cfg_base_url()

    mascot = await generate_mascot_message(
        f"celebrating: just finished '{step['description']}'",
        model=model, system_prompt=prompt, base_url=base_url,
    )
    if not await db.mark_step_done(step_id, mascot):
        raise HTTPException(400, "Step is already done.")

    return {"status": "done", "mascot_message": mascot}


@app.post("/api/steps/{step_id}/snooze")
async def snooze_step(step_id: str):
    if not await db.get_step(step_id):
        raise HTTPException(404, "Step not found.")

    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    mascot = "No rush, little leaf! Even sloths rest between branches. 🌿"
    if not await db.snooze_step(step_id, tomorrow, mascot):
        raise HTTPException(400, "Could not snooze step.")

    return {"status": "snoozed", "until": tomorrow, "mascot_message": mascot}


@app.post("/api/steps/{step_id}/shrink")
async def shrink_step(step_id: str):
    if not check_ai_rate_limit():
        raise HTTPException(429, "Too many AI requests.")

    step = await db.get_step(step_id)
    if not step:
        raise HTTPException(404, "Step not found.")

    model = await _effective_model()
    prompt = await _effective_prompt()
    base_url = _cfg_base_url()

    new_steps = await shrink_step_with_ai(
        step_description=step["description"],
        model=model, system_prompt=prompt, base_url=base_url,
    )
    if len(new_steps) < 2:
        raise HTTPException(500, "Could not shrink step further.")

    first_id, rest_ids = await db.shrink_step(step_id, new_steps)
    first_row = await db.get_step(first_id)
    rest_rows = [await db.get_step(sid) for sid in rest_ids]

    return ShrinkResponse(
        new_step=_row_to_step(first_row),       # type: ignore[arg-type]
        remaining_steps=[_row_to_step(r) for r in rest_rows if r],
        original_id=step_id,
        undo_token=step_id,
    )


@app.post("/api/steps/{step_id}/undo-shrink")
async def undo_shrink(step_id: str):
    if not await db.undo_shrink(step_id):
        raise HTTPException(404, "Original step not found or not shrunk.")
    return {"status": "restored", "original_step_id": step_id}


# ---------------------------------------------------------------------------
# Wins
# ---------------------------------------------------------------------------

@app.get("/api/wins", response_model=WinsResponse)
async def get_wins():
    wins, fully_finished = await db.get_wins()
    return WinsResponse(
        wins=[
            WinEntry(
                step_id=w["step_id"],
                task_id=w["task_id"],
                description=w["description"],
                completed_at=w["completed_at"],
                task_raw_text=w["task_raw_text"],
                mascot_message=w.get("mascot_message"),
            )
            for w in wins
        ],
        fully_finished_tasks=fully_finished,
        total_wins=len(wins),
    )


# ---------------------------------------------------------------------------
# Export / Wipe
# ---------------------------------------------------------------------------

@app.get("/api/export")
async def export_data():
    data = await db.export_all()
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": "attachment; filename=dread_eater_export.json"},
    )


@app.post("/api/wipe")
async def wipe_data(request: Request):
    body = await request.json()
    if body.get("confirm") != "WIPE_EVERYTHING":
        raise HTTPException(400, "Confirm with {'confirm': 'WIPE_EVERYTHING'}.")
    await db.wipe_all()
    return {"status": "wiped"}


# ---------------------------------------------------------------------------
# Retry artifacts (called from morning UI when night runner was offline)
# ---------------------------------------------------------------------------

@app.post("/api/retry-artifacts")
async def retry_artifacts():
    if not check_ai_rate_limit():
        raise HTTPException(429, "Too many AI requests.")

    model = await _effective_model()
    prompt = await _effective_prompt()
    base_url = _cfg_base_url()

    tasks = await db.get_tasks_with_stale_artifacts()
    updated = 0
    for task in tasks[:3]:   # max 3 per request to avoid timeouts
        try:
            analysis = await analyze_task(
                raw_text=task["raw_text"],
                context_text=task.get("context_text"),
                model=model, system_prompt=prompt, base_url=base_url,
            )
            if analysis.prepared_artifacts:
                await db.update_task_artifacts(
                    task["id"], [a.model_dump() for a in analysis.prepared_artifacts]
                )
                updated += 1
        except Exception:
            pass

    await db.set_config_value("night_runner_offline_note", "")
    return {"status": "ok", "updated": updated}


# ---------------------------------------------------------------------------
# SPA catch-all — serve index.html for all non-API routes
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return FileResponse(str(_FRONTEND / "index.html"))


@app.get("/{path:path}")
async def spa_fallback(path: str):
    # Never serve files outside the frontend directory
    requested = (_FRONTEND / path).resolve()
    if not str(requested).startswith(str(_FRONTEND.resolve())):
        raise HTTPException(403, "Forbidden")
    if requested.is_file():
        return FileResponse(str(requested))
    return FileResponse(str(_FRONTEND / "index.html"))
