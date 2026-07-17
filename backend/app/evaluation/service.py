"""
EvaluationService: 评价 → 画像更新 → 路径调整 完整闭环。

评价通过后自动触发 ProfileAgent 生成新画像版本并持久化，
同时触发 PlannerAgent 生成调整后的学习路径。此模块是 Agent2
Day2 的核心集成点。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from app.database import Repository
from app.schemas import (
    EvaluationResult,
    EvaluationSubmission,
    LearningPath,
    ProfileChatRequest,
    StudentProfile,
)

from .evaluator import EvaluationValidationError

logger = logging.getLogger(__name__)


class ProfileAgentProtocol(Protocol):
    """ProfileAgent 的最小接口协议，避免循环依赖。"""

    async def extract(
        self,
        request: ProfileChatRequest,
        previous: StudentProfile | None,
    ) -> Any: ...


class PlannerAgentProtocol(Protocol):
    """PlannerAgent 的最小接口协议，避免循环依赖。"""

    async def generate(
        self,
        profile: StudentProfile,
        previous_path: LearningPath | None = None,
        previous_path_id: str | None = None,
        evaluation_summary: str | None = None,
        target_topics: list[str] | None = None,
    ) -> LearningPath: ...


class EvaluationAgentProtocol(Protocol):
    """Persisted-quiz evaluator interface used by the service."""

    def bind_repository(self, repository: Repository) -> None: ...

    async def evaluate(
        self,
        submission: EvaluationSubmission,
        *,
        expected_topic: str,
    ) -> tuple[EvaluationResult, dict, dict]: ...


@dataclass
class EvaluationResultModel:
    """评价闭环的完整返回值。"""

    result: EvaluationResult
    updated_profile: StudentProfile | None
    updated_path: LearningPath | None


class EvaluationService:
    """评价 → 画像 → 路径的完整闭环服务。

    调用方式：:

        service = EvaluationService(
            evaluator=EvaluationAgent(),
            profile_agent=request.app.state.profile_agent,
            planner_agent=request.app.state.planner_agent,
            repository=request.app.state.repository,
        )
        response = await service.process(submission)
    """

    def __init__(
        self,
        evaluator: EvaluationAgentProtocol,
        profile_agent: ProfileAgentProtocol,
        planner_agent: PlannerAgentProtocol,
        repository: Repository,
    ) -> None:
        self._evaluator = evaluator
        self._profile_agent = profile_agent
        self._planner_agent = planner_agent
        self._repository = repository
        self._evaluator.bind_repository(repository)

    async def process(
        self,
        submission: EvaluationSubmission,
    ) -> EvaluationResultModel:
        """执行评价 → 画像更新 → 路径调整 闭环。

        Returns:
            EvaluationResultModel containing the evaluation result and any
            updated profile/path objects that were persisted.
        """
        path = self._repository.get_path(submission.path_id)
        if path is None:
            raise EvaluationValidationError(
                f"learning path not found: {submission.path_id}"
            )
        if path.student_id != submission.student_id:
            raise EvaluationValidationError(
                "learning path does not belong to student_id"
            )
        path_step = next(
            (item for item in path.steps if item.step == submission.step),
            None,
        )
        if path_step is None:
            raise EvaluationValidationError(
                "step does not exist in the submitted learning path"
            )

        # 1. 使用持久化 Quiz 的答案键执行评价
        result, profile_updates, path_updates = await self._evaluator.evaluate(
            submission,
            expected_topic=path_step.topic,
        )

        updated_profile: StudentProfile | None = None
        updated_path: LearningPath | None = None

        # 2. 若评价要求画像更新，触发 ProfileAgent 创建新版本
        if result.profile_update_required:
            updated_profile = await self._trigger_profile_update(
                submission, result, profile_updates
            )

        # 3. 若评价要求路径调整，触发 PlannerAgent 生成新路径
        if result.path_update_required:
            updated_path = await self._trigger_path_update(
                submission, result, path_updates
            )

        return EvaluationResultModel(
            result=result,
            updated_profile=updated_profile,
            updated_path=updated_path,
        )

    async def _trigger_profile_update(
        self,
        submission: EvaluationSubmission,
        result: EvaluationResult,
        profile_updates: dict,
    ) -> StudentProfile | None:
        """触发 ProfileAgent 创建新画像版本并持久化。"""
        from app.schemas.profile import ChatMessage

        previous = self._repository.get_latest_profile(submission.student_id)
        if previous is None:
            logger.warning(
                "profile_update_skipped: no existing profile for student_id=%s",
                submission.student_id,
            )
            return None

        # 构建评价摘要消息，作为 ProfileAgent 的对话输入
        evaluation_message = self._build_evaluation_message(submission, result)

        evaluation_summary = ChatMessage(
            message_id=f"eval-{result.evaluation_id}",
            role="user",
            content=evaluation_message,
        )

        profile_request = ProfileChatRequest(
            student_id=submission.student_id,
            conversation_id=f"eval-conv-{result.evaluation_id}",
            messages=[evaluation_summary],
            evaluation_summary=evaluation_message[:500],
        )

        try:
            profile_response = await self._profile_agent.extract(
                profile_request, previous
            )
            self._repository.save_profile(profile_response.profile)
            logger.info(
                "profile_updated student_id=%s old_version=%d new_version=%d",
                submission.student_id,
                previous.version,
                profile_response.profile.version,
            )
            return profile_response.profile
        except Exception as exc:
            logger.error("profile_update_failed: %s", exc)
            return None

    async def _trigger_path_update(
        self,
        submission: EvaluationSubmission,
        result: EvaluationResult,
        path_updates: dict,
    ) -> LearningPath | None:
        """触发 PlannerAgent 生成调整后的学习路径并持久化。"""
        # 获取当前画像（可能刚被更新）
        profile = self._repository.get_latest_profile(submission.student_id)
        if profile is None:
            logger.warning(
                "path_update_skipped: no profile for student_id=%s",
                submission.student_id,
            )
            return None

        previous_path = self._repository.get_path(submission.path_id)

        # 构建评价摘要
        evaluation_summary = (
            f"第{result.step}步评价结果：掌握度{result.mastery_score:.0%}，"
            f"{'通过' if result.passed else '未通过'}。"
            f"薄弱知识点：{'、'.join(result.weak_topics) if result.weak_topics else '无'}。"
            f"反馈：{result.feedback[:200]}"
        )

        try:
            new_path = await self._planner_agent.generate(
                profile,
                previous_path=previous_path,
                previous_path_id=submission.path_id,
                evaluation_summary=evaluation_summary,
                target_topics=path_updates.get("revisit_topics") or None,
            )
            if not new_path.adjustment_reason:
                weak_topics = "、".join(result.weak_topics) or "当前学习步骤"
                new_path = new_path.model_copy(
                    update={"adjustment_reason": f"根据评价结果优先复习：{weak_topics}"}
                )
            self._repository.save_path(new_path)
            logger.info(
                "path_updated student_id=%s new_path_id=%s",
                submission.student_id,
                new_path.path_id,
            )
            return new_path
        except Exception as exc:
            logger.error("path_update_failed: %s", exc)
            return None

    @staticmethod
    def _build_evaluation_message(
        submission: EvaluationSubmission,
        result: EvaluationResult,
    ) -> str:
        """将评价结果转为自然语言消息，供 ProfileAgent 提取事实。"""
        weak = "、".join(result.weak_topics) if result.weak_topics else "无"
        return (
            f"学习评价证据（来源：evaluation）：经过第{result.step}步学习，"
            f"我完成了练习测验，掌握度为{result.mastery_score:.0%}，"
            f"{'通过了测评' if result.passed else '未通过测评'}。"
            f"薄弱知识点：{weak}。"
            f"用时约{submission.time_spent_minutes}分钟。"
            f"{result.feedback[:300]}"
        )
