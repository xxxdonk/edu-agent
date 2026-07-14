from __future__ import annotations

import re
from uuid import uuid4

from app.schemas import LearningPath, LearningPathStep, ResourceType, StudentProfile
from app.schemas.common import Difficulty, utc_now


class PlannerAgent:
    """Day-1 input-dependent planner; the knowledge-aware LLM planner replaces it on Day 2."""

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
            topic = PlannerAgent._goal_topic(goal)
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
            return min(90, max(20, profile.time_budget.value.minutes_per_day))
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
