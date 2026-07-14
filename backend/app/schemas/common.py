from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Difficulty(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class ResourceType(StrEnum):
    EXPLANATION = "explanation"
    MIND_MAP = "mind_map"
    QUIZ = "quiz"
    READING = "reading"
    CODING = "coding"


class ErrorDetail(ApiModel):
    code: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class ErrorResponse(ApiModel):
    error: ErrorDetail
