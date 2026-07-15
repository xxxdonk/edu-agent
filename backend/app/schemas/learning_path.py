from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from .common import ApiModel, ResourceType, utc_now
from .profile import StudentProfile


class LearningPathStep(ApiModel):
    step: int = Field(ge=1)
    topic: str
    learning_goal: str
    reason: str
    recommended_resources: list[ResourceType] = Field(min_length=1)
    completion_criteria: list[str] = Field(min_length=1)
    estimated_minutes: int = Field(gt=0)
    prerequisites: list[str] = Field(default_factory=list)


class LearningPath(ApiModel):
    path_id: str
    student_id: str
    profile_version: int = Field(ge=1)
    course: str
    status: Literal["active", "superseded", "completed"] = "active"
    steps: list[LearningPathStep] = Field(min_length=1)
    adjustment_reason: str | None = None
    generation_mode: Literal["development_rule_based", "llm_structured"]
    created_at: datetime = Field(default_factory=utc_now)


class PathGenerateRequest(ApiModel):
    student_id: str = Field(min_length=1, max_length=128)
    profile: StudentProfile | None = None
    previous_path_id: str | None = None
    evaluation_summary: str | None = Field(default=None, max_length=4000)


class PathGenerateResponse(ApiModel):
    path: LearningPath
