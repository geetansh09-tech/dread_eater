"""
Ollama HTTP client.

All communication goes to localhost:11434 only.  No other network calls.

Parse pipeline:
  raw LLM text
    → strip <think>…</think>          (qwen3 reasoning blocks)
    → _extract_json()                  (handles code-fences, embedded JSON)
    → Pydantic validation (LLMAnalysis)
    → on failure: retry once with explicit schema reminder
    → on second failure: FALLBACK_ANALYSIS (hardcoded safe defaults)
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

import httpx

from backend.models import LLMAnalysis, PreparedArtifact
from backend.security import strip_think_blocks

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen3:4b"
DEFAULT_TIMEOUT = 120.0
MASCOT_TIMEOUT = 30.0

# ---------------------------------------------------------------------------
# Safe fallback (returned when both LLM attempts fail)
# ---------------------------------------------------------------------------

FALLBACK_ANALYSIS = LLMAnalysis(
    dread_score=5,
    dread_reason="Something about this feels unclear or uncomfortable",
    first_step="Spend 2 minutes writing down everything you know about this task",
    first_step_duration_min=2,
    ladder=[
        {"description": "Identify the single biggest blocker", "duration_min": 5},
        {"description": "Break that blocker into three smaller pieces", "duration_min": 10},
        {"description": "Do the easiest piece right now", "duration_min": 10},
    ],
    prepared_artifacts=[],
    is_medical_legal_financial=False,
    mascot_message="Even sloths start somewhere. Just one tiny thing! 🦥",
)

# ---------------------------------------------------------------------------
# JSON schema the LLM must produce
# ---------------------------------------------------------------------------

_JSON_SCHEMA = """\
Return ONLY valid JSON — no markdown fences, no explanation text, nothing else.
Use this exact structure:
{
  "dread_score": <integer 1-10>,
  "dread_reason": "<one sentence why this task feels dreaded>",
  "first_step": "<action completable in under 2 minutes>",
  "first_step_duration_min": <1 or 2>,
  "ladder": [
    {"description": "<step>", "duration_min": <integer 1-10>},
    ... (3 to 6 items)
  ],
  "prepared_artifacts": [
    {
      "type": "<email_draft|checklist|phone_script|outline>",
      "title": "<short title>",
      "content": "<full ready-to-use text>"
    }
  ],
  "is_medical_legal_financial": <true|false>,
  "mascot_message": "<max 15 words, sloth voice, gentle & funny, no guilt>"
}"""

_SHRINK_SCHEMA = """\
Return ONLY valid JSON — no markdown, no explanation.
{
  "steps": [
    {"description": "<micro-step>", "duration_min": <integer 1-5>},
    ... (2 to 4 items)
  ]
}"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Try to parse JSON from raw LLM output, handling common wrapping formats."""
    text = text.strip()

    # 1. Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Markdown code block (```json … ``` or ``` … ```)
    code_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if code_match:
        try:
            return json.loads(code_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. First standalone JSON object
    obj_match = re.search(r"\{[\s\S]*\}", text)
    if obj_match:
        try:
            return json.loads(obj_match.group(0))
        except json.JSONDecodeError:
            pass

    return None


async def _generate(
    model: str,
    prompt: str,
    base_url: str = OLLAMA_BASE_URL,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """POST to /api/generate, return stripped response text."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{base_url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
        )
        resp.raise_for_status()
        raw: str = resp.json().get("response", "")
        return strip_think_blocks(raw)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def analyze_task(
    raw_text: str,
    context_text: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    system_prompt: str = "",
    base_url: str = OLLAMA_BASE_URL,
) -> LLMAnalysis:
    """
    Ask the LLM to analyse a dreaded task.
    Retries once on bad JSON; returns FALLBACK_ANALYSIS on persistent failure.
    """
    context_block = f"\n\nADDITIONAL CONTEXT:\n{context_text}" if context_text else ""

    base_prompt = (
        f"{system_prompt}\n\n"
        "Analyse this dreaded task and return structured JSON:\n\n"
        f"TASK:\n{raw_text}{context_block}\n\n"
        f"{_JSON_SCHEMA}"
    )

    for attempt in range(2):
        prompt = base_prompt
        if attempt == 1:
            prompt += (
                "\n\nIMPORTANT: Your previous response was not valid JSON. "
                "Return ONLY the raw JSON object, starting with { and ending with }."
            )
        try:
            raw = await _generate(model, prompt, base_url)
            data = _extract_json(raw)
            if data is not None:
                return LLMAnalysis(**data)
        except Exception:
            pass  # fall through to retry / fallback

    return FALLBACK_ANALYSIS


async def shrink_step_with_ai(
    step_description: str,
    model: str = DEFAULT_MODEL,
    system_prompt: str = "",
    base_url: str = OLLAMA_BASE_URL,
) -> List[Dict[str, Any]]:
    """
    Break a step into 2-4 micro-steps (each ≤ 5 min).
    Falls back to a simple 2-part split on failure.
    """
    base_prompt = (
        f"{system_prompt}\n\n"
        "A person finds this step too big to start. "
        "Break it into 2 to 4 micro-steps, each under 5 minutes.\n\n"
        f"STEP: {step_description}\n\n"
        f"{_SHRINK_SCHEMA}"
    )

    for attempt in range(2):
        prompt = base_prompt
        if attempt == 1:
            prompt += (
                "\n\nReturn ONLY the raw JSON with a 'steps' array. "
                "Nothing else."
            )
        try:
            raw = await _generate(model, prompt, base_url)
            data = _extract_json(raw)
            if data and isinstance(data.get("steps"), list):
                steps = [
                    {
                        "description": str(s.get("description", ""))[:500],
                        "duration_min": min(int(s.get("duration_min", 3)), 5),
                    }
                    for s in data["steps"][:4]
                    if s.get("description")
                ]
                if len(steps) >= 2:
                    return steps
        except Exception:
            pass

    # Hard fallback — split the original text in two
    half = step_description[:120]
    return [
        {"description": f"Start: {half}", "duration_min": 2},
        {"description": f"Finish: {half}", "duration_min": 3},
    ]


async def generate_mascot_message(
    context: str,
    model: str = DEFAULT_MODEL,
    system_prompt: str = "",
    base_url: str = OLLAMA_BASE_URL,
) -> str:
    """
    Generate a ≤15-word sloth mascot quip.
    Falls back to a hardcoded message if the model is unavailable or slow.
    """
    prompt = (
        f"{system_prompt}\n\n"
        "Write ONE short message for a cartoon sloth mascot.\n"
        f"Context: {context}\n"
        "Rules:\n"
        "- Maximum 15 words\n"
        "- Warm, gentle, funny sloth personality\n"
        "- NEVER guilt-trip or judge\n"
        "- No JSON, no quotes, no markdown — just the message text"
    )
    try:
        raw = await _generate(model, prompt, base_url, timeout=MASCOT_TIMEOUT)
        # Strip stray punctuation and JSON artifacts
        raw = re.sub(r'[`"{}\[\]]', "", raw).strip()
        words = raw.split()[:15]
        msg = " ".join(words)
        return msg if msg else "Slow and steady, little buddy. You've got this! 🦥"
    except Exception:
        return "Slow and steady, little buddy. You've got this! 🦥"


async def list_models(base_url: str = OLLAMA_BASE_URL) -> List[str]:
    """Return model names available in the local Ollama instance."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{base_url}/api/tags")
            resp.raise_for_status()
            return [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        return []


async def check_ollama_alive(base_url: str = OLLAMA_BASE_URL) -> bool:
    """Ping Ollama. Returns False if unreachable (never raises)."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base_url}/api/tags")
            return resp.status_code == 200
    except Exception:
        return False
