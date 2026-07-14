from __future__ import annotations

from datetime import datetime
from typing import Generic, Literal, TypeVar
from uuid import uuid4

from pydantic import Field

from .common import ApiModel, Difficulty, utc_now

T = TypeVar("T")


class FieldEvidence(ApiModel):
    source: Literal["conversation", "evaluation", "inference", "system_default"]
    quote: str
    message_id: str | None = None


class ProfileField(ApiModel, Generic[T]):
    value: T
    evidence: list[FieldEvidence] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class TimeBudget(ApiModel):
    minutes_per_day: int = Field(ge=0, le=1440)
    days_per_week: int = Field(ge=1, le=7, default=5)


class ChatMessage(ApiModel):
    message_id: str = Field(default_factory=lambda: str(uuid4()))
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class StudentProfile(ApiModel):
    student_id: str
    version: int = Field(ge=1)
    major: ProfileField[str | None]
    course: ProfileField[str | None]
    knowledge_level: ProfileField[Difficulty | None]
    learning_goals: ProfileField[list[str]]
    weak_topics: ProfileField[list[str]]
    learning_history: ProfileField[list[str]]
    cognitive_style: ProfileField[str | None]
    language_preference: ProfileField[str | None]
    resource_preference: ProfileField[list[str]]
    time_budget: ProfileField[TimeBudget | None]
    evidence: list[FieldEvidence] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    updated_at: datetime = Field(default_factory=utc_now)


class ProfileChatRequest(ApiModel):
    student_id: str = Field(min_length=1, max_length=128)
    conversation_id: str | None = None
    messages: list[ChatMessage] = Field(min_length=1, max_length=100)
    evaluation_summary: str | None = Field(default=None, max_length=4000)


class ProfileChatResponse(ApiModel):
    profile: StudentProfile
    missing_dimensions: list[str]
    next_question: str | None
    is_complete: bool
    extraction_mode: Literal["development_heuristic", "llm_structured"]
