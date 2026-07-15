from __future__ import annotations

import logging

from app.orchestrator import SharedAgentContext
from app.schemas import Resource, ResourceType
from app.schemas.common import Difficulty

logger = logging.getLogger(__name__)


class ReviewerAgent:
    agent_name = "reviewer_agent"

    async def review(
        self,
        resource: Resource,
        context: SharedAgentContext,
    ) -> Resource:
        issues: list[str] = []

        self._check_source_references(resource, issues)
        self._check_difficulty_match(resource, context, issues)
        self._check_personalization(resource, context, issues)
        self._check_content_integrity(resource, issues)
        self._check_resource_type_format(resource, issues)

        if issues:
            logger.warning("review_issues resource_id=%s issues=%s", resource.resource_id, issues)
            return resource.model_copy(
                update={
                    "review_status": "needs_revision",
                    "personalization_reason": (
                        resource.personalization_reason
                        + f" [审校问题：{'；'.join(issues)}]"
                    ),
                }
            )

        return resource.model_copy(update={"review_status": "approved"})

    @staticmethod
    def _check_source_references(resource: Resource, issues: list[str]) -> None:
        if not resource.source_references:
            issues.append("缺少知识库来源引用")
            return
        for ref in resource.source_references:
            if not ref.source_id or not ref.locator:
                issues.append(f"来源引用不完整：source_id={ref.source_id}")
                return

    @staticmethod
    def _check_difficulty_match(
        resource: Resource,
        context: SharedAgentContext,
        issues: list[str],
    ) -> None:
        profile_level = context.profile.knowledge_level.value
        if profile_level and resource.difficulty.value != profile_level:
            issues.append(
                f"难度不匹配：资源={resource.difficulty.value}，学生水平={profile_level}"
            )

    @staticmethod
    def _check_personalization(
        resource: Resource,
        context: SharedAgentContext,
        issues: list[str],
    ) -> None:
        if len(resource.personalization_reason) < 10:
            issues.append("个性化理由过短，缺乏充分说明")
        weak_topics = context.profile.weak_topics.value or []
        if weak_topics and not any(
            wt.lower() in resource.personalization_reason.lower() for wt in weak_topics
        ):
            issues.append("个性化理由未提及学生薄弱点")

    @staticmethod
    def _check_content_integrity(resource: Resource, issues: list[str]) -> None:
        if len(resource.content) < 50:
            issues.append("内容过短，可能不完整")
        if not resource.title or len(resource.title) < 3:
            issues.append("标题过短或缺失")

    @staticmethod
    def _check_resource_type_format(resource: Resource, issues: list[str]) -> None:
        expected_formats: dict[ResourceType, set[str]] = {
            ResourceType.EXPLANATION: {"markdown", "text"},
            ResourceType.MIND_MAP: {"mermaid"},
            ResourceType.QUIZ: {"json", "markdown"},
            ResourceType.READING: {"markdown", "text"},
            ResourceType.CODING: {"python", "markdown"},
        }
        allowed = expected_formats.get(resource.resource_type, set())
        if resource.content_format not in allowed:
            issues.append(
                f"content_format 不匹配：{resource.resource_type.value} "
                f"期望 {allowed}，实际 {resource.content_format}"
            )
