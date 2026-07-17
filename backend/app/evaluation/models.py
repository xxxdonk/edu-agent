"""Pydantic models for the LLM-driven EvaluationAgent output."""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import ApiModel


class QuestionVerdict(str):
    """Verdict enum-like literal; kept as plain str for Pydantic compatibility."""


class AnswerJudgment(ApiModel):
    """Single-question judgment produced by the LLM evaluator."""

    question_id: str
    verdict: str = Field(description="correct | partial | incorrect")
    score: float = Field(ge=0.0, le=100.0)
    reasoning: str
    topic: str


class EvaluationDraft(ApiModel):
    """Aggregate evaluation draft produced by the LLM evaluator."""

    judgments: list[AnswerJudgment] = Field(default_factory=list)
    mastery_score: float = Field(ge=0.0, le=1.0)
    passed: bool
    weak_topics: list[str] = Field(default_factory=list)
    feedback: str
