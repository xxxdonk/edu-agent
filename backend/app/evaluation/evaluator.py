"""EvaluationAgent — LLM-driven & heuristic dual-path answer evaluator.

When ``enable_llm`` is True and an ``LLMClient`` instance is available, the
agent uses structured LLM output to judge every student answer against
standard answers or course knowledge.  Otherwise it falls back to the
Phase‑1 heuristic path (length‑based correctness) so that the system
remains functional even without an LLM backend.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from uuid import uuid4

from pydantic import ValidationError

from app.llm import LLMClient, LLMError, LLMMessage
from app.llm.errors import safe_error_summary
from app.schemas import EvaluationResult, EvaluationSubmission

from .models import EvaluationDraft
from .prompts import EVALUATION_SYSTEM_PROMPT

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

    # ------------------------------------------------------------------
    # Constructor
    # ------------------------------------------------------------------

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        *,
        enable_llm: bool = False,
    ) -> None:
        self._llm_client = llm_client
        self._enable_llm = enable_llm

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def evaluate(
        self,
        submission: EvaluationSubmission,
    ) -> tuple[EvaluationResult, dict, dict]:
        """Evaluate a batch of answers and return (result, profile suggestions, path suggestions)."""

        if self._enable_llm and self._llm_client is not None:
            try:
                return await self._evaluate_with_llm(submission)
            except (LLMError, ValidationError, ValueError) as error:
                logger.warning(
                    "evaluation_fallback_to_heuristic reason=%s",
                    safe_error_summary(error),
                )
        return self._evaluate_heuristic(submission)

    # ==================================================================
    # LLM path
    # ==================================================================

    async def _evaluate_with_llm(
        self,
        submission: EvaluationSubmission,
    ) -> tuple[EvaluationResult, dict, dict]:
        """Use the LLM client to judge every answer via structured output."""

        # Build payload: every question with its metadata and the student response
        questions_payload: list[dict] = []
        for answer in submission.answers:
            meta = self._resolve_question(answer.question_id, answer.response)
            questions_payload.append(
                {
                    "question_id": meta.question_id,
                    "topic": meta.topic,
                    "difficulty": meta.level,
                    "max_points": meta.points,
                    "standard_answer": meta.correct_answer or "",
                    "student_response": answer.response,
                }
            )

        system_prompt = EVALUATION_SYSTEM_PROMPT
        user_content = json.dumps(
            {
                "student_id": submission.student_id,
                "path_id": submission.path_id,
                "step": submission.step,
                "questions": questions_payload,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

        draft: EvaluationDraft = await self._llm_client.generate_structured(
            system_prompt=system_prompt,
            messages=[LLMMessage(role="user", content=user_content)],
            response_model=EvaluationDraft,
        )

        return self._build_result_from_draft(submission, draft)

    # ==================================================================
    # Heuristic fallback (Phase‑1 mock)
    # ==================================================================

    def _evaluate_heuristic(
        self,
        submission: EvaluationSubmission,
    ) -> tuple[EvaluationResult, dict, dict]:
        total_score = 0.0
        max_score = 0.0
        weak_topics: list[str] = []
        feedback_parts: list[str] = []

        for answer in submission.answers:
            question_meta = self._resolve_question(answer.question_id, answer.response)
            max_score += question_meta.points

            if self._is_correct(answer.response, question_meta.correct_answer):
                total_score += question_meta.points
                feedback_parts.append(f"题目 {answer.question_id}：正确 ✓")
            elif self._is_partial(answer.response, question_meta.correct_answer):
                total_score += question_meta.points * 0.3
                feedback_parts.append(
                    f"题目 {answer.question_id}：部分正确 / 需要复习 {question_meta.topic}"
                )
                weak_topics.append(question_meta.topic)
            else:
                feedback_parts.append(
                    f"题目 {answer.question_id}：错误 / 需要重点复习 {question_meta.topic}"
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

        profile_update_suggestions = self._build_profile_updates(
            submission, mastery_score, passed, weak_topics_deduped
        )
        path_update_suggestions = self._build_path_updates(
            submission, mastery_score, passed, weak_topics_deduped
        )

        return (
            EvaluationResult(
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
            ),
            profile_update_suggestions,
            path_update_suggestions,
        )

    # ==================================================================
    # Shared helpers
    # ==================================================================

    @staticmethod
    def _resolve_question(question_id: str, response: str) -> _QuestionMeta:
        """Dynamically infer question metadata from the question_id naming convention."""

        qid_lower = question_id.lower()

        # Infer difficulty
        if any(kw in qid_lower for kw in ("advanced", "hard", "综合", "complex")):
            level = "advanced"
        elif any(kw in qid_lower for kw in ("intermediate", "medium", "mid", "应用")):
            level = "intermediate"
        else:
            level = "basic"

        # Infer topic
        topic_keywords = {
            "overview": "机器学习概述",
            "linear": "线性回归",
            "logistic": "逻辑回归",
            "tree": "决策树",
            "svm": "支持向量机",
            "cluster": "聚类",
            "nn": "神经网络基础",
            "neural": "神经网络基础",
            "eval": "模型评估与过拟合",
            "metric": "模型评估与过拟合",
            "过拟合": "模型评估与过拟合",
        }
        topic = "综合"
        for key, val in topic_keywords.items():
            if key in qid_lower:
                topic = val
                break

        # Infer points from response length
        response_clean = response.strip()
        if len(response_clean) > 200:
            points = 5.0
        elif len(response_clean) > 50:
            points = 3.0
        else:
            points = 2.0

        return _QuestionMeta(
            question_id=question_id,
            level=level,
            topic=topic,
            correct_answer="",
            points=points,
        )

    @staticmethod
    def _is_correct(response: str, correct_answer: str) -> bool:
        response_clean = response.strip().lower().replace(" ", "")
        if not correct_answer:
            return len(response_clean) > 50 and len(response_clean) < 5000
        correct_clean = correct_answer.strip().lower().replace(" ", "")
        if response_clean == correct_clean:
            return True
        return correct_clean in response_clean[:100]

    @staticmethod
    def _is_partial(response: str, correct_answer: str) -> bool:
        response_clean = response.strip().lower().replace(" ", "")
        if not correct_answer:
            return 10 < len(response_clean) <= 50
        correct_clean = correct_answer.strip().lower().replace(" ", "")
        return len(response_clean) > 5 and not (
            response_clean == correct_clean or correct_clean in response_clean[:100]
        )

    def _build_result_from_draft(
        self,
        submission: EvaluationSubmission,
        draft: EvaluationDraft,
    ) -> tuple[EvaluationResult, dict, dict]:
        """Convert the parsed EvaluationDraft into the canonical tuple."""

        feedback_lines: list[str] = []
        for judgment in draft.judgments:
            symbol = {"correct": "✓", "partial": "△", "incorrect": "✗"}.get(
                judgment.verdict, "?"
            )
            feedback_lines.append(
                f"题目 {judgment.question_id}：{symbol} {judgment.reasoning}"
            )

        feedback = f"{draft.feedback}\n\n---\n逐题详情：\n" + "\n".join(feedback_lines)

        result = EvaluationResult(
            evaluation_id=str(uuid4()),
            student_id=submission.student_id,
            path_id=submission.path_id,
            step=submission.step,
            mastery_score=round(draft.mastery_score, 4),
            passed=draft.passed,
            weak_topics=list(dict.fromkeys(draft.weak_topics)),
            feedback=feedback,
            profile_update_required=not draft.passed,
            path_update_required=not draft.passed,
        )

        profile_updates = self._build_profile_updates(
            submission, result.mastery_score, result.passed, result.weak_topics
        )
        path_updates = self._build_path_updates(
            submission, result.mastery_score, result.passed, result.weak_topics
        )
        return result, profile_updates, path_updates

    # ==================================================================
    # Profile / Path suggestion builders (shared by both paths)
    # ==================================================================

    @staticmethod
    def _build_profile_updates(
        submission: EvaluationSubmission,
        mastery_score: float,
        passed: bool,
        weak_topics: list[str],
    ) -> dict:
        weak_topics_list = weak_topics if weak_topics else []

        if mastery_score >= 0.85:
            knowledge_level_adjustment = "advanced"
        elif mastery_score >= 0.6:
            knowledge_level_adjustment = "intermediate"
        else:
            knowledge_level_adjustment = "basic"

        cognitive_style_evidence = None
        time_spent = submission.time_spent_minutes
        num_answers = len(submission.answers)
        if time_spent > 0 and num_answers > 0:
            avg_time = time_spent / num_answers
            if avg_time < 1:
                cognitive_style_evidence = "快速作答风格：学生倾向于直觉反应而非深入分析"
            elif avg_time > 10:
                cognitive_style_evidence = "深思熟虑风格：学生花费较长时间仔细推敲答案"

        resource_preference_adjustment = None
        if not passed:
            if weak_topics:
                resource_preference_adjustment = [
                    f"建议增加 {t} 相关的练习和解释类资源" for t in weak_topics[:3]
                ]

        return {
            "weak_topics": weak_topics_list,
            "knowledge_level_adjustment": knowledge_level_adjustment,
            "cognitive_style_evidence": cognitive_style_evidence,
            "resource_preference_adjustment": resource_preference_adjustment,
        }

    @staticmethod
    def _build_path_updates(
        submission: EvaluationSubmission,
        mastery_score: float,
        passed: bool,
        weak_topics: list[str],
    ) -> dict:
        revisit_topics = weak_topics if weak_topics else []

        next_topics_map = {
            "机器学习概述": ["线性回归"],
            "线性回归": ["逻辑回归"],
            "逻辑回归": ["决策树", "支持向量机"],
            "决策树": ["支持向量机", "聚类"],
            "支持向量机": ["聚类", "神经网络基础"],
            "聚类": ["神经网络基础"],
            "神经网络基础": ["模型评估与过拟合"],
            "模型评估与过拟合": [],
        }
        next_topics_all: list[str] = []
        for topic in weak_topics if passed else (weak_topics or ["机器学习概述"]):
            next_topics_all.extend(next_topics_map.get(topic, []))

        next_topics = list(dict.fromkeys(next_topics_all))

        if passed:
            priority_adjustment = "学生已通过当前阶段评估，可按原路径继续推进"
        else:
            priority_adjustment = (
                f"学生未通过评估（掌握度 {mastery_score:.0%}），"
                f"建议优先复习薄弱知识点后再进入下一阶段"
            )

        if mastery_score >= 0.8:
            estimated_extra = 15
        elif mastery_score >= 0.6:
            estimated_extra = 30
        else:
            estimated_extra = 60

        return {
            "revisit_topics": revisit_topics,
            "next_topics": next_topics,
            "priority_adjustment": priority_adjustment,
            "estimated_extra_minutes": estimated_extra,
        }
