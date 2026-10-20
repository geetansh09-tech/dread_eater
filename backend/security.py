"""
Security helpers: input sanitisation, CSP headers, rate limiting, body-size cap.

Nothing here makes network calls — it's all local enforcement.
"""
from __future__ import annotations

import re
import threading
import time
from collections import defaultdict
from typing import Callable

import bleach
from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ALLOWED_HTML_TAGS: list = []          # strip ALL tags
MAX_BODY_BYTES: int = 64 * 1024        # 64 KB hard cap
AI_RATE_LIMIT: int = 10               # max AI calls per minute

# Keywords that suggest medical / legal / financial content
_MLF_KEYWORDS: frozenset = frozenset({
    "diagnosis", "diagnose", "symptom", "medication", "prescription",
    "lawyer", "lawsuit", "legal advice", "court", "attorney", "sue", "suing",
    "tax", "tax return", "irs", "hmrc", "invest", "stock market",
    "financial advice", "medical advice", "doctor", "hospital",
    "insurance claim", "legal action", "bankruptcy",
})

# ---------------------------------------------------------------------------
# Text sanitisation
# ---------------------------------------------------------------------------

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_think_blocks(text: str) -> str:
    """Remove <think>…</think> blocks emitted by reasoning models (e.g. qwen3)."""
    return _THINK_RE.sub("", text).strip()


def sanitize_text(text: str) -> str:
    """
    Strip all HTML tags (using bleach), then strip <think> blocks.
    Safe to call on any user-supplied string before storage or LLM submission.
    """
    if not text:
        return ""
    cleaned = bleach.clean(text, tags=_ALLOWED_HTML_TAGS, strip=True)
    cleaned = strip_think_blocks(cleaned)
    return cleaned.strip()


# ---------------------------------------------------------------------------
# Medical / Legal / Financial detection
# ---------------------------------------------------------------------------

def detect_mlf(text: str) -> bool:
    """Return True if text contains medical, legal, or financial keywords."""
    lower = text.lower()
    return any(kw in lower for kw in _MLF_KEYWORDS)


# ---------------------------------------------------------------------------
# In-memory rate limiter (per "client" — always 127.0.0.1 in practice)
# ---------------------------------------------------------------------------

_rate_lock = threading.Lock()
_rate_windows: dict = defaultdict(list)


def check_ai_rate_limit(client_key: str = "local") -> bool:
    """
    Returns True if the request is within the rate limit.
    Uses a sliding 60-second window.
    """
    now = time.monotonic()
    with _rate_lock:
        window = [t for t in _rate_windows[client_key] if now - t < 60.0]
        _rate_windows[client_key] = window
        if len(window) >= AI_RATE_LIMIT:
            return False
        _rate_windows[client_key].append(now)
        return True


# ---------------------------------------------------------------------------
# Middleware: security response headers
# ---------------------------------------------------------------------------

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Injects strict security headers on every response.

    CSP blocks all external origins — the only allowed network destination
    is localhost:11434 (Ollama).  All other connections are denied at the
    browser level.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        csp = (
            "default-src 'self'; "
            "connect-src 'self' http://localhost:11434; "
            "img-src 'self' data:; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )

        response.headers["Content-Security-Policy"] = csp
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), "
            "payment=(), usb=(), magnetometer=()"
        )
        # Prevent caching of API responses that contain personal data
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"

        return response


# ---------------------------------------------------------------------------
# Middleware: request body size cap
# ---------------------------------------------------------------------------

class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Rejects requests whose Content-Length exceeds MAX_BODY_BYTES."""

    def __init__(self, app, max_bytes: int = MAX_BODY_BYTES) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        cl = request.headers.get("content-length")
        if cl and int(cl) > self.max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Request body exceeds {self.max_bytes // 1024} KB limit.",
            )
        return await call_next(request)
