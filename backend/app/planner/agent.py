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
from .models import (
    LearningPathDraft,
    PLANNER_RESOURCE_TYPE_VALUES,
    _clean_topic_label,
)
from .prompts import PLANNER_SYSTEM_PROMPT, planner_format_repair_prompt

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
        topics = [
            cleaned
            for item in profile.weak_topics.value
            if (cleaned := _clean_topic_label(item))
        ]
        for goal in profile.learning_goals.value:
            topic = _clean_topic_label(DevelopmentPlannerAgent._goal_topic(goal))
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
        request_id = uuid4().hex[:12]
        fallback_path_id = previous_path.path_id if previous_path else previous_path_id
        logger.info(
            "planner_request_started request_id=%s profile_version=%s replan=%s",
            request_id,
            profile.version,
            bool(previous_path or evaluation_summary),
        )
        if not self._enable_llm or self._llm_client is None:
            path = self._fallback.generate(
                profile,
                previous_path_id=fallback_path_id,
                evaluation_summary=evaluation_summary,
            )
            logger.info(
                "planner_request_completed request_id=%s mode=%s reason=%s",
                request_id,
                path.generation_mode,
                "llm_disabled" if not self._enable_llm else "llm_client_unavailable",
            )
            return path
        try:
            draft = await self._generate_validated_draft(
                profile,
                previous_path,
                evaluation_summary,
                target_topics,
                request_id,
            )
            adjustment_reason = draft.adjustment_reason
            if not adjustment_reason and (previous_path or evaluation_summary):
                adjustment_reason = (
                    f"根据评价结果调整：{evaluation_summary[:200]}"
                    if evaluation_summary
                    else f"基于旧路径 {previous_path.path_id} 重新规划"
                )
            path = LearningPath(
                path_id=str(uuid4()),
                student_id=profile.student_id,
                profile_version=profile.version,
                course=profile.course.value or "机器学习基础",
                steps=[
                    LearningPathStep.model_validate(step.model_dump(mode="json"))
                    for step in draft.steps
                ],
                adjustment_reason=adjustment_reason,
                generation_mode="llm_structured",
                created_at=utc_now(),
            )
            logger.info(
                "planner_request_completed request_id=%s mode=%s",
                request_id,
                path.generation_mode,
            )
            return path
        except (LLMError, ValidationError, ValueError) as error:
            logger.warning(
                "planner_fallback request_id=%s mode=development_rule_based error=%s",
                request_id,
                safe_error_summary(error),
            )
            path = self._fallback.generate(
                profile,
                previous_path_id=fallback_path_id,
                evaluation_summary=evaluation_summary,
            )
            logger.info(
                "planner_request_completed request_id=%s mode=%s",
                request_id,
                path.generation_mode,
            )
            return path

    async def _generate_validated_draft(
        self,
        profile: StudentProfile,
        previous_path: LearningPath | None,
        evaluation_summary: str | None,
        target_topics: list[str] | None,
        request_id: str,
    ) -> LearningPathDraft:
        prompt_payload = self._prompt_payload(
            profile,
            previous_path,
            evaluation_summary,
            target_topics,
        )
        repair_error_summary: str | None = None
        for attempt in range(2):
            system_prompt = (
                planner_format_repair_prompt(repair_error_summary or "unknown")
                if attempt
                else PLANNER_SYSTEM_PROMPT
            )
            try:
                draft = await self._llm_client.generate_structured(
                    system_prompt=system_prompt,
                    messages=[LLMMessage(role="user", content=prompt_payload)],
                    response_model=LearningPathDraft,
                )
                self._validate_draft(draft, profile)
                if attempt:
                    logger.info(
                        "planner_format_repair request_id=%s attempt=2 success=true",
                        request_id,
                    )
                return draft
            except (
                LLMResponseFormatError,
                LLMValidationError,
                ValidationError,
            ) as error:
                repair_error_summary = self._validation_error_summary(error)
                self._log_invalid_resource_enums(error, request_id, attempt + 1)
                if attempt:
                    logger.warning(
                        "planner_format_repair request_id=%s attempt=2 success=false error=%s",
                        request_id,
                        repair_error_summary,
                    )
                    raise
                logger.warning(
                    "planner_format_repair request_id=%s attempt=1 requested=true error=%s",
                    request_id,
                    repair_error_summary,
                )
        raise LLMValidationError("planner format repair exhausted")

    @staticmethod
    def _prompt_payload(
        profile: StudentProfile,
        previous_path: LearningPath | None,
        evaluation_summary: str | None,
        target_topics: list[str] | None,
    ) -> str:
        priority_topics = PlannerAgent._normalize_topics(
            target_topics or list(profile.weak_topics.value)
        )
        constraints = {
            "max_minutes_per_step": (
                profile.time_budget.value.minutes_per_day
                if profile.time_budget.value
                else 45
            ),
            "priority_topics": priority_topics,
            "step_numbers_must_be_contiguous": True,
            "topics_must_be_unique": True,
            "prerequisites_must_reference_earlier_topics": True,
        }
        if previous_path or evaluation_summary:
            payload = {
                "task": "replan_after_evaluation",
                "profile_summary": PlannerAgent._profile_summary(profile),
                "unmastered_topics": priority_topics,
                "current_path_summary": (
                    PlannerAgent._compact_previous_path(previous_path)
                    if previous_path
                    else None
                ),
                "adjustment_reason": evaluation_summary,
                "constraints": constraints,
            }
        else:
            payload = {
                "task": "create_initial_path",
                "profile_summary": PlannerAgent._profile_summary(profile),
                "target_topics": priority_topics,
                "constraints": constraints,
            }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _profile_summary(profile: StudentProfile) -> dict[str, object]:
        return {
            "major": profile.major.value,
            "course": profile.course.value,
            "knowledge_level": profile.knowledge_level.value,
            "learning_goals": list(profile.learning_goals.value),
            "weak_topics": PlannerAgent._normalize_topics(profile.weak_topics.value),
            "cognitive_style": profile.cognitive_style.value,
            "resource_preference": list(profile.resource_preference.value),
            "time_budget_minutes": (
                profile.time_budget.value.minutes_per_day
                if profile.time_budget.value
                else 45
            ),
        }

    @staticmethod
    def _normalize_topics(topics: list[str]) -> list[str]:
        normalized = [
            cleaned for item in topics if (cleaned := _clean_topic_label(item))
        ]
        return list(dict.fromkeys(normalized))

    @staticmethod
    def _validation_error_summary(error: BaseException) -> str:
        validation_error = PlannerAgent._extract_validation_error(error)
        if validation_error is None:
            return safe_error_summary(error)

        details: list[str] = []
        for item in validation_error.errors(include_url=False)[:4]:
            location = ".".join(str(part) for part in item.get("loc", ())) or "root"
            error_type = item.get("type", "validation_error")
            detail = f"{location}: {error_type}"
            if error_type == "enum" and "recommended_resources" in location:
                detail += (
                    f" value={json.dumps(PlannerAgent._safe_enum_value(item.get('input')), ensure_ascii=False)}"
                    f" allowed={PlannerAgent._resource_types_json()}"
                )
            details.append(detail)
        return "pydantic_validation_error: " + "; ".join(details)

    @staticmethod
    def _extract_validation_error(error: BaseException) -> ValidationError | None:
        if isinstance(error, ValidationError):
            return error
        if isinstance(error.__cause__, ValidationError):
            return error.__cause__
        return None

    @staticmethod
    def _safe_enum_value(value: object) -> str:
        if not isinstance(value, str):
            return f"<{type(value).__name__}>"
        return re.sub(r"\s+", " ", value.strip())[:64] or "<empty>"

    @staticmethod
    def _resource_types_json() -> str:
        return json.dumps(
            list(PLANNER_RESOURCE_TYPE_VALUES),
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @staticmethod
    def _log_invalid_resource_enums(
        error: BaseException,
        request_id: str,
        attempt: int,
    ) -> None:
        validation_error = PlannerAgent._extract_validation_error(error)
        if validation_error is None:
            return
        for item in validation_error.errors(include_url=False):
            location = ".".join(str(part) for part in item.get("loc", ())) or "root"
            if item.get("type") != "enum" or "recommended_resources" not in location:
                continue
            logger.warning(
                "planner_invalid_enum request_id=%s attempt=%s field=%s value=%s allowed=%s",
                request_id,
                attempt,
                location,
                json.dumps(
                    PlannerAgent._safe_enum_value(item.get("input")),
                    ensure_ascii=False,
                ),
                PlannerAgent._resource_types_json(),
            )

    @staticmethod
    def _compact_previous_path(path: LearningPath) -> dict[str, object]:
        return {
            "course": path.course,
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
