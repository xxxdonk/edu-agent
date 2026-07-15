from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import uuid4

from app.schemas import EvaluationResult, EvaluationSubmission

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _QuestionMeta:
    question_id: str
    level: str
    topic: str
    correct_answer: str
    points: float


class EvaluationAgent:
    agent_name = "evaluation_agent"

    async def evaluate(
        self,
        submission: EvaluationSubmission,
    ) -> EvaluationResult:
        total_score = 0.0
        max_score = 0.0
        weak_topics: list[str] = []
        feedback_parts: list[str] = []

        for answer in submission.answers:
            question_meta = self._resolve_question(answer.question_id)
            max_score += question_meta.points
            if self._is_correct(answer.response, question_meta.correct_answer):
                total_score += question_meta.points
                feedback_parts.append(f"题目 {answer.question_id}：正确 ✓")
            else:
                total_score += question_meta.points * 0.3
                feedback_parts.append(
                    f"题目 {answer.question_id}：部分正确 / 需要复习 {question_meta.topic}"
                )
                weak_topics.append(question_meta.topic)

        mastery_score = round(total_score / max(max_score, 1.0), 4)
        passed = mastery_score >= 0.6
        weak_topics_deduped = list(dict.fromkeys(weak_topics))

        feedback = "\n".join(feedback_parts)
        if passed:
            feedback += f"\n\n总体评价：通过（掌握度 {mastery_score:.0%}）"
        else:
            feedback += (
                f"\n\n总体评价：未通过（掌握度 {mastery_score:.0%}），"
                f"建议重点复习：{'、'.join(weak_topics_deduped)}"
            )

        return EvaluationResult(
            evaluation_id=str(uuid4()),
            student_id=submission.student_id,
            path_id=submission.path_id,
            step=submission.step,
            mastery_score=mastery_score,
            passed=passed,
            weak_topics=weak_topics_deduped,
            feedback=feedback,
            profile_update_required=not passed,
            path_update_required=not passed,
        )

    @staticmethod
    def _resolve_question(question_id: str) -> _QuestionMeta:
        default_meta = {
            "q1": _QuestionMeta("q1", "basic", "概念理解", "A", 2.0),
            "q2": _QuestionMeta("q2", "basic", "核心原理", "B", 2.0),
            "q3": _QuestionMeta("q3", "intermediate", "算法流程", "梯度下降", 3.0),
            "q4": _QuestionMeta("q4", "advanced", "综合应用", "局部最优", 3.0),
        }
        return default_meta.get(question_id, _QuestionMeta(question_id, "basic", "综合", "待定", 2.0))

    @staticmethod
    def _is_correct(response: str, correct_answer: str) -> bool:
        response_clean = response.strip().lower().replace(" ", "")
        correct_clean = correct_answer.strip().lower().replace(" ", "")
        if response_clean == correct_clean:
            return True
        return correct_clean in response_clean[:100]
