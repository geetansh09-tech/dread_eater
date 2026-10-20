"""
pytest shared fixtures and mocked Ollama client.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from backend.models import LLMAnalysis, PreparedArtifact

# ---------------------------------------------------------------------------
# Shared mock data
# ---------------------------------------------------------------------------

MOCK_ANALYSIS = LLMAnalysis(
    dread_score=7,
    dread_reason="Fear of bad news and an unclear first step",
    first_step="Open the letter and read the first line",
    first_step_duration_min=2,
    ladder=[
        {"description": "Write down what needs doing", "duration_min": 5},
        {"description": "Gather necessary documents", "duration_min": 10},
        {"description": "Take action", "duration_min": 10},
    ],
    prepared_artifacts=[
        PreparedArtifact(
            type="email_draft",
            title="Draft Reply",
            content="Dear Sir/Madam, I am writing to...",
        )
    ],
    is_medical_legal_financial=False,
    mascot_message="One tiny leaf at a time, little one!",
)

MOCK_SHRINK_STEPS = [
    {"description": "Step one: read the first sentence", "duration_min": 2},
    {"description": "Step two: write one word", "duration_min": 3},
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_ollama_analyze():
    with patch(
        "backend.ollama_client.analyze_task",
        new=AsyncMock(return_value=MOCK_ANALYSIS),
    ) as m:
        yield m


@pytest.fixture
def mock_ollama_shrink():
    with patch(
        "backend.ollama_client.shrink_step_with_ai",
        new=AsyncMock(return_value=MOCK_SHRINK_STEPS),
    ) as m:
        yield m


@pytest.fixture
def mock_generate_bad():
    """Simulates Ollama returning gibberish."""
    with patch(
        "backend.ollama_client._generate",
        new=AsyncMock(return_value="not json at all !!!!"),
    ) as m:
        yield m
