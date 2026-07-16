from __future__ import annotations

import json
import logging
import re
from uuid import uuid4

from pydantic import ValidationError

from app.llm import (
    LLMClient,
    LLMError,
    LLMMessage,
    LLMResponseFormatError,
    LLMValidationError,
)
from app.llm.errors import safe_error_summary
from app.schemas import LearningPath, LearningPathStep, ResourceType, StudentProfile
from app.schemas.common import Difficulty, utc_now
from .models import LearningPathDraft
from .prompts import PLANNER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class DevelopmentPlannerAgent:
    """Input-dependent rule-based fallback for unavailable structured planning."""

    mode = "development_rule_based"

    def generate(
        self,
        profile: StudentProfile,
        previous_path_id: str | None = None,
        evaluation_summary: str | None = None,
    ) -> LearningPath:
        topics = self._topics(profile)
        minutes = self._minutes_per_step(profile)
        resources = self._resource_order(profile)
        major = profile.major.value or "当前专业"
        level = profile.knowledge_level.value or Difficulty.BEGINNER

        steps: list[LearningPathStep] = []
        for index, topic in enumerate(topics, start=1):
            prerequisites = [topics[index - 2]] if index > 1 else []
            criteria = self._criteria(topic, level)
            steps.append(
                LearningPathStep(
                    step=index,
                    topic=topic,
                    learning_goal=f"掌握{topic}并能在{major}相关情境中解释或应用",
                    reason=self._reason(profile, topic, index, evaluation_summary),
                    recommended_resources=resources,
                    completion_criteria=criteria,
                    estimated_minutes=minutes,
                    prerequisites=prerequisites,
                )
            )

        return LearningPath(
            path_id=str(uuid4()),
            student_id=profile.student_id,
            profile_version=profile.version,
            course=profile.course.value or "机器学习基础",
            steps=steps,
            adjustment_reason=(
                f"根据评价结果调整：{evaluation_summary[:200]}"
                if evaluation_summary
                else (f"替换学习路径 {previous_path_id}" if previous_path_id else None)
            ),
            generation_mode=self.mode,
            created_at=utc_now(),
        )

    @staticmethod
    def _topics(profile: StudentProfile) -> list[str]:
        topics = list(profile.weak_topics.value)
        for goal in profile.learning_goals.value:
            topic = DevelopmentPlannerAgent._goal_topic(goal)
            if topic not in topics:
                topics.append(topic)
        if not topics:
            topics = [profile.course.value or "机器学习基础"]
        return topics[:5]

    @staticmethod
    def _goal_topic(goal: str) -> str:
        topic = goal.strip()
        for prefix in ("目标是", "我想", "想要", "希望", "最后能", "为了"):
            if topic.startswith(prefix):
                topic = topic[len(prefix) :].strip()
                break
        for prefix in ("理解", "掌握", "学会"):
            if topic.startswith(prefix):
                return topic[len(prefix) :].strip()
        match = re.match(r"使用\s*(.+?)\s*完成\s*(.+)", topic)
        if match:
            project = re.sub(r"^一个", "", match.group(2)).strip()
            return f"{match.group(1)}{project}".strip()
        return topic

    @staticmethod
    def _minutes_per_step(profile: StudentProfile) -> int:
        if profile.time_budget.value:
            return min(90, max(5, profile.time_budget.value.minutes_per_day))
        return 45

    @staticmethod
    def _resource_order(profile: StudentProfile) -> list[ResourceType]:
        preference_map = {
            "讲解文档": ResourceType.EXPLANATION,
            "思维导图": ResourceType.MIND_MAP,
            "分层练习题": ResourceType.QUIZ,
            "拓展阅读": ResourceType.READING,
            "代码实践案例": ResourceType.CODING,
        }
        preferred = [
            preference_map[item]
            for item in profile.resource_preference.value
            if item in preference_map
        ]
        level = profile.knowledge_level.value
        defaults = (
            [ResourceType.READING, ResourceType.CODING, ResourceType.QUIZ]
            if level == Difficulty.ADVANCED
            else [ResourceType.EXPLANATION, ResourceType.MIND_MAP, ResourceType.QUIZ]
        )
        return list(dict.fromkeys([*preferred, *defaults]))

    @staticmethod
    def _criteria(topic: str, level: Difficulty) -> list[str]:
        criteria = [f"能用自己的语言解释{topic}", "相关练习正确率达到80%"]
        if level != Difficulty.BEGINNER:
            criteria.append(f"能完成一个与{topic}相关的代码或案例分析")
        return criteria

    @staticmethod
    def _reason(
        profile: StudentProfile,
        topic: str,
        index: int,
        evaluation_summary: str | None,
    ) -> str:
        if evaluation_summary and topic in evaluation_summary:
            return f"最新评价显示{topic}仍需加强，因此优先安排"
        if topic in profile.weak_topics.value:
            return f"画像证据显示{topic}是当前薄弱点，安排在第{index}步重点突破"
        return f"该主题直接服务于学习目标，并结合当前画像安排在第{index}步"


class PlannerAgent:
    """Structured LLM planner with an explicit rule-based fallback."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        *,
        enable_llm: bool = False,
        fallback: DevelopmentPlannerAgent | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._enable_llm = enable_llm
        self._fallback = fallback or DevelopmentPlannerAgent()

    async def generate(
        self,
        profile: StudentProfile,
        previous_path: LearningPath | None = None,
        previous_path_id: str | None = None,
        evaluation_summary: str | None = None,
        target_topics: list[str] | None = None,
    ) -> LearningPath:
        fallback_path_id = previous_path.path_id if previous_path else previous_path_id
        if not self._enable_llm or self._llm_client is None:
            return self._fallback.generate(
                profile,
                previous_path_id=fallback_path_id,
                evaluation_summary=evaluation_summary,
            )
        try:
            draft = await self._generate_validated_draft(
                profile,
                previous_path,
                evaluation_summary,
                target_topics,
            )
            adjustment_reason = draft.adjustment_reason
            if not adjustment_reason and (previous_path or evaluation_summary):
                adjustment_reason = (
                    f"根据评价结果调整：{evaluation_summary[:200]}"
                    if evaluation_summary
                    else f"基于旧路径 {previous_path.path_id} 重新规划"
                )
            return LearningPath(
                path_id=str(uuid4()),
                student_id=profile.student_id,
                profile_version=profile.version,
                course=profile.course.value or "机器学习基础",
                steps=draft.steps,
                adjustment_reason=adjustment_reason,
                generation_mode="llm_structured",
                created_at=utc_now(),
            )
        except (LLMError, ValidationError, ValueError) as error:
            logger.warning("planner_llm_fallback error=%s", safe_error_summary(error))
            return self._fallback.generate(
                profile,
                previous_path_id=fallback_path_id,
                evaluation_summary=evaluation_summary,
            )

    async def _generate_validated_draft(
        self,
        profile: StudentProfile,
        previous_path: LearningPath | None,
        evaluation_summary: str | None,
        target_topics: list[str] | None,
    ) -> LearningPathDraft:
        prompt_payload = self._prompt_payload(
            profile,
            previous_path,
            evaluation_summary,
            target_topics,
        )
        for attempt in range(2):
            system_prompt = PLANNER_SYSTEM_PROMPT
            if attempt:
                system_prompt += (
                    "\nFORMAT REPAIR: Regenerate the complete JSON object once. "
                    "Follow the schema and every constraint exactly; do not add "
                    "fields, commentary, or Markdown."
                )
            try:
                draft = await self._llm_client.generate_structured(
                    system_prompt=system_prompt,
                    messages=[LLMMessage(role="user", content=prompt_payload)],
                    response_model=LearningPathDraft,
                )
                self._validate_draft(draft, profile)
                if attempt:
                    logger.info("planner_format_repair success=true")
                return draft
            except (
                LLMResponseFormatError,
                LLMValidationError,
                ValidationError,
            ) as error:
                if attempt:
                    raise
                logger.warning(
                    "planner_format_repair requested=true error=%s",
                    safe_error_summary(error),
                )
        raise LLMValidationError("planner format repair exhausted")

    @staticmethod
    def _prompt_payload(
        profile: StudentProfile,
        previous_path: LearningPath | None,
        evaluation_summary: str | None,
        target_topics: list[str] | None,
    ) -> str:
        payload = {
            "profile": PlannerAgent._compact_profile(profile),
            "course": profile.course.value or "机器学习基础",
            "constraints": {
                "max_minutes_per_step": (
                    profile.time_budget.value.minutes_per_day
                    if profile.time_budget.value
                    else 45
                ),
                "priority_topics": list(profile.weak_topics.value),
                "step_numbers_must_be_contiguous": True,
                "topics_must_be_unique": True,
            },
            "previous_path": (
                PlannerAgent._compact_previous_path(previous_path)
                if previous_path
                else None
            ),
            "evaluation_summary": evaluation_summary,
            "target_topics": target_topics or [],
            "knowledge_base_available": False,
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _compact_profile(profile: StudentProfile) -> dict[str, object]:
        compact: dict[str, object] = {
            "student_id": profile.student_id,
            "version": profile.version,
            "confidence": profile.confidence,
        }
        for field_name in (
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
        ):
            profile_field = getattr(profile, field_name)
            value = profile_field.value
            compact[field_name] = {
                "value": value.model_dump(mode="json")
                if hasattr(value, "model_dump")
                else value,
                "confidence": profile_field.confidence,
            }
        return compact

    @staticmethod
    def _compact_previous_path(path: LearningPath) -> dict[str, object]:
        return {
            "path_id": path.path_id,
            "profile_version": path.profile_version,
            "course": path.course,
            "status": path.status,
            "steps": [
                {
                    "step": step.step,
                    "topic": step.topic,
                    "learning_goal": step.learning_goal,
                    "completion_criteria": step.completion_criteria,
                    "estimated_minutes": step.estimated_minutes,
                    "prerequisites": step.prerequisites,
                }
                for step in path.steps
            ],
            "adjustment_reason": path.adjustment_reason,
            "generation_mode": path.generation_mode,
        }

    @staticmethod
    def _validate_draft(
        draft: LearningPathDraft,
        profile: StudentProfile,
    ) -> None:
        expected_steps = list(range(1, len(draft.steps) + 1))
        if [step.step for step in draft.steps] != expected_steps:
            raise LLMValidationError("learning path steps are not consecutively ordered")

        normalized_topics = [step.topic.strip().casefold() for step in draft.steps]
        if len(normalized_topics) != len(set(normalized_topics)):
            raise LLMValidationError("learning path contains duplicate topics")

        earlier_topics: set[str] = set()
        for step in draft.steps:
            if any(prerequisite not in earlier_topics for prerequisite in step.prerequisites):
                raise LLMValidationError(
                    "learning path prerequisite does not reference an earlier topic"
                )
            earlier_topics.add(step.topic)

        calculated_total = sum(step.estimated_minutes for step in draft.steps)
        if calculated_total != draft.total_estimated_minutes:
            raise LLMValidationError("learning path total time is inconsistent")

        if profile.time_budget.value:
            daily_budget = profile.time_budget.value.minutes_per_day
            if any(step.estimated_minutes > daily_budget for step in draft.steps):
                raise LLMValidationError(
                    "learning path step exceeds the student's daily time budget"
                )

        searchable_text = " ".join(
            [
                *[step.topic for step in draft.steps],
                *[step.learning_goal for step in draft.steps],
                *[step.reason for step in draft.steps],
            ]
        )
        if any(
            phrase in searchable_text
            for phrase in ("已检索知识库", "根据知识库检索", "知识库已验证")
        ):
            raise LLMValidationError("planner falsely claimed knowledge-base retrieval")
