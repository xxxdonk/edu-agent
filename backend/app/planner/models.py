from __future__ import annotations

from pydantic import Field

from app.schemas.common import ApiModel
from app.schemas.learning_path import LearningPathStep


class LearningPathDraft(ApiModel):
    steps: list[LearningPathStep] = Field(min_length=1, max_length=10)
    total_estimated_minutes: int = Field(gt=0)
    adjustment_reason: str | None = Field(default=None, max_length=1000)
