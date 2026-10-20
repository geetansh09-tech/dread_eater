"""
Pydantic models for requests, responses, and internal data structures.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class EnergyLevel(str, Enum):
    sleepy = "sleepy"
    okay = "okay"
    awake = "awake"


class StepStatus(str, Enum):
    pending = "pending"
    done = "done"
    snoozed = "snoozed"
    shrunk = "shrunk"   # the original step that was later split


# ---------------------------------------------------------------------------
# LLM output model
# ---------------------------------------------------------------------------

class PreparedArtifact(BaseModel):
    """A ready-to-use draft that the model wrote for the user."""
    type: str   # email_draft | checklist | phone_script | outline
    title: str
    content: str


class LLMAnalysis(BaseModel):
    """Strict schema for the JSON the LLM must return."""
    dread_score: int = Field(..., ge=1, le=10)
    dread_reason: str = Field(..., max_length=300)
    first_step: str = Field(..., max_length=600)
    first_step_duration_min: int = Field(default=2, ge=1, le=2)
    ladder: List[dict] = Field(default_factory=list)
    prepared_artifacts: List[PreparedArtifact] = Field(default_factory=list)
    is_medical_legal_financial: bool = False
    mascot_message: str = Field(
        default="One tiny step at a time, friend! 🦥",
        max_length=120,
    )

    @field_validator("ladder")
    @classmethod
    def validate_ladder(cls, v: list) -> list:
        validated = []
        for item in v[:6]:           # hard-cap at 6 ladder steps
            if isinstance(item, dict) and "description" in item:
                validated.append(
                    {
                        "description": str(item.get("description", ""))[:500],
                        "duration_min": min(int(item.get("duration_min", 10)), 10),
                    }
                )
        return validated

    @field_validator("dread_reason", "first_step", "mascot_message", mode="before")
    @classmethod
    def strip_str(cls, v: object) -> str:
        return str(v).strip() if v else ""


# ---------------------------------------------------------------------------
# API request / response models
# ---------------------------------------------------------------------------

class DumpRequest(BaseModel):
    raw_text: str = Field(..., min_length=1, max_length=4096)
    context_text: Optional[str] = Field(default=None, max_length=8192)


class TaskResponse(BaseModel):
    id: str
    raw_text: str
    dread_score: int
    dread_reason: str
    first_step: str
    ladder: list
    prepared_artifacts: list
    is_medical_legal_financial: bool
    created_at: str


class StepResponse(BaseModel):
    id: str
    task_id: str
    description: str
    order_idx: int
    duration_min: int
    status: str
    snoozed_until: Optional[str] = None
    completed_at: Optional[str] = None
    is_shrunken: bool = False
    shrunk_from: Optional[str] = None
    task_raw_text: Optional[str] = None
    mascot_message: Optional[str] = None


class TodayResponse(BaseModel):
    step: Optional[StepResponse] = None
    energy_level: Optional[str] = None
    total_tasks: int = 0
    completed_today: int = 0
    ollama_offline_note: Optional[str] = None


class EnergyRequest(BaseModel):
    energy_level: EnergyLevel


class WinEntry(BaseModel):
    step_id: str
    task_id: str
    description: str
    completed_at: str
    task_raw_text: str
    mascot_message: Optional[str] = None


class WinsResponse(BaseModel):
    wins: List[WinEntry]
    fully_finished_tasks: int
    total_wins: int


class ShrinkResponse(BaseModel):
    new_step: StepResponse
    remaining_steps: List[StepResponse]
    original_id: str
    undo_token: str   # == original step ID — pass to /undo-shrink


class ConfigResponse(BaseModel):
    model: str
    system_prompt: str
    available_models: List[str]


class UpdateConfigRequest(BaseModel):
    model: Optional[str] = None
    system_prompt: Optional[str] = Field(default=None, max_length=4096)


class HealthResponse(BaseModel):
    status: str
    model: str
    ollama_alive: bool
    db_path: str
