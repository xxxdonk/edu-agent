from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .common import ApiModel, utc_now


class EvaluationAnswer(ApiModel):
    question_id: str
    response: str


class EvaluationSubmission(ApiModel):
    student_id: str
    path_id: str
    step: int = Field(ge=1)
    answers: list[EvaluationAnswer] = Field(min_length=1)
    time_spent_minutes: int = Field(ge=0)


class EvaluationResult(ApiModel):
    evaluation_id: str
    student_id: str
    path_id: str
    step: int
    mastery_score: float = Field(ge=0.0, le=1.0)
    passed: bool
    weak_topics: list[str] = Field(default_factory=list)
    feedback: str
    profile_update_required: bool
    path_update_required: bool
    evaluated_at: datetime = Field(default_factory=utc_now)
