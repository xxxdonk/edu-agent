from __future__ import annotations

from pydantic import Field

from app.schemas.common import ApiModel, Difficulty
from app.schemas.profile import ProfileField, TimeBudget


class ProfileExtractionDraft(ApiModel):
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
    next_question: str | None = Field(default=None, max_length=500)
