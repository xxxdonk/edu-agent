"""EvaluationAgent backed by persisted Quiz resources and answer keys."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from uuid import uuid4

from app.database import Repository
from app.schemas import EvaluationResult, EvaluationSubmission, ResourceType


class EvaluationValidationError(ValueError):
    """The submitted answer set cannot be matched to the generated quiz."""


class EvaluationQuestionNotFoundError(LookupError):
    """A referenced persisted quiz or question does not exist."""


class EvaluationConfigurationError(RuntimeError):
    """EvaluationAgent is missing a dependency required for real grading."""


@dataclass(slots=True)
class _QuestionMeta:
    question_id: str
    level: str
    topic: str
    correct_answer: str
    points: float
    question_type: str


class EvaluationAgent:
    """Grade answers against the persisted Quiz resource answer key."""

    agent_name = "evaluation_agent"

    def __init__(self, repository: Repository | None = None) -> None:
        self._repository = repository

    def bind_repository(self, repository: Repository) -> None:
        """Bind the repository that owns persisted quiz and task data."""
        self._repository = repository

    def _require_repository(self) -> Repository:
        if self._repository is None:
            raise EvaluationConfigurationError(
                "EvaluationAgent repository is not configured; pass repository "
                "to EvaluationAgent or bind it through EvaluationService"
            )
        return self._repository

    async def evaluate(
        self,
        submission: EvaluationSubmission,
        *,
        expected_topic: str,
    ) -> tuple[EvaluationResult, dict, dict]:
        self._require_repository()
        answer_ids = [answer.question_id for answer in submission.answers]
        if len(answer_ids) != len(set(answer_ids)):
            raise EvaluationValidationError("question_id must not be submitted more than once")

        total_score = 0.0
        max_score = 0.0
        weak_topics: list[str] = []
        feedback_parts: list[str] = []

        for answer in submission.answers:
            question_meta = self._resolve_question(
                answer.question_id,
                student_id=submission.student_id,
                expected_topic=expected_topic,
            )
            max_score += question_meta.points
            fraction = self._score_answer(answer.response, question_meta)
            total_score += question_meta.points * fraction

            if fraction >= 1.0:
                feedback_parts.append(f"题目 {answer.question_id}：正确")
            elif fraction > 0:
                feedback_parts.append(
                    f"题目 {answer.question_id}：部分正确，需要复习 {question_meta.topic}"
                )
                weak_topics.append(question_meta.topic)
            else:
                feedback_parts.append(
                    f"题目 {answer.question_id}：回答不正确，需要重点复习 {question_meta.topic}"
                )
                weak_topics.append(question_meta.topic)

        mastery_score = round(total_score / max(max_score, 1.0), 4)
        passed = mastery_score >= 0.6
        weak_topics_deduped = list(dict.fromkeys(weak_topics))
        feedback = "\n".join(feedback_parts)
        if passed:
            feedback += f"\n\n总体评价：通过（掌握度 {mastery_score:.0%}）。"
        else:
            topics = "、".join(weak_topics_deduped) or expected_topic
            feedback += (
                f"\n\n总体评价：未通过（掌握度 {mastery_score:.0%}），"
                f"建议重点复习：{topics}。"
            )

        profile_update_suggestions = self._build_profile_updates(
            submission, mastery_score, passed, weak_topics_deduped
        )
        path_update_suggestions = self._build_path_updates(
            mastery_score, passed, weak_topics_deduped
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
                profile_update_required=not passed or bool(weak_topics_deduped),
                path_update_required=not passed or bool(weak_topics_deduped),
            ),
            profile_update_suggestions,
            path_update_suggestions,
        )

    def _resolve_question(
        self,
        question_id: str,
        *,
        student_id: str,
        expected_topic: str,
    ) -> _QuestionMeta:
        resource_id, separator, local_question_id = question_id.partition("::")
        if not separator or not resource_id or not local_question_id:
            raise EvaluationValidationError(
                "question_id is not bound to a persisted quiz resource"
            )

        repository = self._require_repository()
        resource = repository.get_resource(resource_id)
        if resource is None:
            raise EvaluationQuestionNotFoundError(f"quiz resource not found: {resource_id}")
        if resource.resource_type != ResourceType.QUIZ:
            raise EvaluationValidationError("question_id does not reference a quiz resource")
        if self._resource_student_id(resource_id) != student_id:
            raise EvaluationValidationError("quiz resource does not belong to student_id")
        if self._normalize_text(resource.target_topic) != self._normalize_text(expected_topic):
            raise EvaluationValidationError("quiz resource does not belong to the submitted path step")

        document = self._parse_quiz_document(resource.content)
        question = next(
            (
                item
                for item in document["questions"]
                if isinstance(item, dict)
                and str(item.get("id") or "") in {question_id, local_question_id}
            ),
            None,
        )
        if question is None:
            raise EvaluationQuestionNotFoundError(f"quiz question not found: {question_id}")
        correct_answer = str(question.get("answer") or "").strip()
        if not correct_answer:
            raise EvaluationValidationError("quiz question has no persisted answer key")

        level = str(question.get("level") or "basic").lower()
        points = {"basic": 1.0, "intermediate": 2.0, "advanced": 3.0}.get(level, 1.0)
        return _QuestionMeta(
            question_id=question_id,
            level=level,
            topic=resource.target_topic,
            correct_answer=correct_answer,
            points=points,
            question_type=str(question.get("type") or "short_answer").lower(),
        )

    def _resource_student_id(self, resource_id: str) -> str | None:
        repository = self._require_repository()
        with repository.database.connect() as connection:
            row = connection.execute(
                "SELECT task_id FROM resources WHERE resource_id = ?",
                (resource_id,),
            ).fetchone()
        if not row or not row["task_id"]:
            return None
        task = repository.get_task(str(row["task_id"]))
        return task.student_id if task else None

    @staticmethod
    def _parse_quiz_document(content: str) -> dict:
        cleaned = content.strip()
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL | re.IGNORECASE)
        if fenced:
            cleaned = fenced.group(1).strip()
        try:
            document = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise EvaluationValidationError("persisted quiz content is invalid JSON") from exc
        if not isinstance(document, dict) or not isinstance(document.get("questions"), list):
            raise EvaluationValidationError("persisted quiz has no questions array")
        return document

    @classmethod
    def _score_answer(cls, response: str, question: _QuestionMeta) -> float:
        response_clean = cls._normalize_text(response)
        correct_clean = cls._normalize_text(question.correct_answer)
        if not response_clean:
            return 0.0

        if question.question_type == "single_choice":
            response_choice = cls._choice_letter(response)
            correct_choice = cls._choice_letter(question.correct_answer)
            if response_choice and correct_choice:
                return 1.0 if response_choice == correct_choice else 0.0

        if response_clean == correct_clean or correct_clean in response_clean:
            return 1.0

        expected_units = cls._character_bigrams(correct_clean)
        response_units = cls._character_bigrams(response_clean)
        if not expected_units:
            return 0.0
        coverage = len(expected_units & response_units) / len(expected_units)
        if coverage >= 0.65:
            return 1.0
        if coverage >= 0.25:
            return 0.5
        return 0.0

    @staticmethod
    def _choice_letter(value: str) -> str | None:
        match = re.search(r"(?:^|\b)([A-H])(?:\b|[.、:：])", value.strip().upper())
        return match.group(1) if match else None

    @staticmethod
    def _normalize_text(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).lower()
        return "".join(character for character in normalized if character.isalnum())

    @staticmethod
    def _character_bigrams(value: str) -> set[str]:
        if len(value) < 2:
            return {value} if value else set()
        return {value[index : index + 2] for index in range(len(value) - 1)}

    @staticmethod
    def _build_profile_updates(
        submission: EvaluationSubmission,
        mastery_score: float,
        passed: bool,
        weak_topics: list[str],
    ) -> dict:
        if mastery_score >= 0.85:
            knowledge_level_adjustment = "advanced"
        elif mastery_score >= 0.6:
            knowledge_level_adjustment = "intermediate"
        else:
            knowledge_level_adjustment = "beginner"

        cognitive_style_evidence = None
        if submission.answers and submission.time_spent_minutes > 0:
            average_minutes = submission.time_spent_minutes / len(submission.answers)
            if average_minutes < 1:
                cognitive_style_evidence = "评价显示作答速度较快，建议增加推导与检查步骤"
            elif average_minutes > 10:
                cognitive_style_evidence = "评价显示单题思考时间较长，建议提供分步提示"

        return {
            "weak_topics": weak_topics,
            "knowledge_level_adjustment": knowledge_level_adjustment,
            "cognitive_style_evidence": cognitive_style_evidence,
            "resource_preference_adjustment": (
                [f"增加 {topic} 的代码示例、图示和分层练习" for topic in weak_topics[:3]]
                if not passed
                else None
            ),
            "evidence_source": "evaluation",
        }

    @staticmethod
    def _build_path_updates(
        mastery_score: float,
        passed: bool,
        weak_topics: list[str],
    ) -> dict:
        return {
            "revisit_topics": weak_topics,
            "next_topics": [] if weak_topics else ["下一学习路径步骤"],
            "priority_adjustment": (
                "当前评价已通过，可按原路径继续推进"
                if passed and not weak_topics
                else f"掌握度 {mastery_score:.0%}，应先复习评价识别出的薄弱知识点"
            ),
            "estimated_extra_minutes": 15 if mastery_score >= 0.8 else 30 if mastery_score >= 0.6 else 60,
        }
