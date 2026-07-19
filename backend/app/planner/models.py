from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from pydantic import Field, model_validator

from app.schemas.common import ApiModel, ResourceType


_TOPIC_PREFIX = re.compile(r"^(?:(?:知识点|点|主题)\s*[:：]\s*)+")
PLANNER_RESOURCE_TYPE_VALUES = tuple(item.value for item in ResourceType)
_RESOURCE_TYPE_ALIASES = {
    "mindmap": ResourceType.MIND_MAP.value,
    "mind-map": ResourceType.MIND_MAP.value,
    "课程讲解": ResourceType.EXPLANATION.value,
    "讲解文档": ResourceType.EXPLANATION.value,
    "思维导图": ResourceType.MIND_MAP.value,
    "分层练习": ResourceType.QUIZ.value,
    "分层练习题": ResourceType.QUIZ.value,
    "拓展阅读": ResourceType.READING.value,
    "代码实践": ResourceType.CODING.value,
    "代码实践案例": ResourceType.CODING.value,
}


def _clean_topic_label(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return _TOPIC_PREFIX.sub("", value.strip()).strip()


def _normalize_resource_type(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    normalized = stripped.casefold()
    if normalized in PLANNER_RESOURCE_TYPE_VALUES:
        return normalized
    return _RESOURCE_TYPE_ALIASES.get(normalized, stripped)


class LearningPathStepDraft(ApiModel):
    """Private Planner output shape; public LearningPathStep stays unchanged."""

    step: int = Field(ge=1)
    topic: str = Field(min_length=1)
    learning_goal: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    recommended_resources: list[ResourceType] = Field(min_length=1)
    completion_criteria: list[str] = Field(min_length=1)
    estimated_minutes: int = Field(gt=0)
    prerequisites: list[str] = Field(default_factory=list)


class LearningPathDraft(ApiModel):
    steps: list[LearningPathStepDraft] = Field(min_length=1, max_length=10)
    total_estimated_minutes: int = Field(gt=0)
    adjustment_reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="before")
    @classmethod
    def normalize_unambiguous_formats(cls, value: Any) -> Any:
        """Normalize representation only; never invent missing learning content."""

        if not isinstance(value, dict):
            return value
        normalized = deepcopy(value)
        steps = normalized.get("steps")
        if isinstance(steps, list):
            for index, raw_step in enumerate(steps, start=1):
                if not isinstance(raw_step, dict):
                    continue
                raw_step["step"] = index
                raw_step["topic"] = _clean_topic_label(raw_step.get("topic"))

                prerequisites = raw_step.get("prerequisites")
                if prerequisites is None:
                    raw_step["prerequisites"] = []
                elif isinstance(prerequisites, list):
                    raw_step["prerequisites"] = [
                        _clean_topic_label(item) for item in prerequisites
                    ]

                resources = raw_step.get("recommended_resources")
                if isinstance(resources, str):
                    resources = [resources]
                if isinstance(resources, list):
                    raw_step["recommended_resources"] = [
                        _normalize_resource_type(item) for item in resources
                    ]

                minutes = raw_step.get("estimated_minutes")
                if isinstance(minutes, str) and minutes.strip().isdigit():
                    raw_step["estimated_minutes"] = int(minutes.strip())

        total = normalized.get("total_estimated_minutes")
        if isinstance(total, str) and total.strip().isdigit():
            normalized["total_estimated_minutes"] = int(total.strip())
        return normalized
