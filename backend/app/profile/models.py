from __future__ import annotations

import re
from typing import Any

from pydantic import Field, model_validator

from app.schemas.common import ApiModel, Difficulty
from app.schemas.profile import ProfileField, TimeBudget


_LIST_VALUE_FIELDS = {
    "learning_goals",
    "weak_topics",
    "learning_history",
    "resource_preference",
}
_PROFILE_FIELD_NAMES = {
    "major",
    "course",
    "knowledge_level",
    "learning_goals",
    "weak_topics",
    "learning_history",
    "cognitive_style",
    "language_preference",
    "resource_preference",
    "time_budget",
}
_WEAK_TOPIC_PREFIX = re.compile(
    r"^(?:(?:薄弱点|知识点|未掌握|需要加强|主题|点)\s*[:：]\s*)+"
)


def _normalize_weak_topics(values: Any) -> Any:
    """Clean explicit labels while preserving ordinary topic punctuation."""

    if not isinstance(values, list):
        return values
    normalized: list[Any] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            normalized.append(value)
            continue
        topic = _WEAK_TOPIC_PREFIX.sub("", value.strip()).strip()
        if not topic or topic in seen:
            continue
        seen.add(topic)
        normalized.append(topic)
    return normalized


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

    @model_validator(mode="before")
    @classmethod
    def normalize_empty_field_consistency(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        normalized = dict(value)
        for field_name in _PROFILE_FIELD_NAMES:
            raw_field = normalized.get(field_name)
            if not isinstance(raw_field, dict):
                continue

            field = dict(raw_field)
            field_value = field.get("value")
            if field_name == "weak_topics":
                field_value = _normalize_weak_topics(field_value)
                field["value"] = field_value
                normalized[field_name] = field
            is_empty = (
                field_value is None
                or field_value == []
                or (isinstance(field_value, str) and not field_value.strip())
            )
            if not is_empty:
                continue

            field["value"] = [] if field_name in _LIST_VALUE_FIELDS else None
            field["evidence"] = []
            field["confidence"] = 0.0
            normalized[field_name] = field
        return normalized
