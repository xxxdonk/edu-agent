"""Tests for EvaluationService integration with Profile/Planner.

These tests verify that evaluation correctly triggers profile updates and
path adjustments per the BE-002 fix.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.database import Repository, SQLiteDatabase
from app.evaluation import EvaluationAgent, EvaluationService
from app.evaluation.evaluator import EvaluationConfigurationError
from app.schemas import (
    Difficulty,
    EvaluationSubmission,
    LearningPath,
    LearningPathStep,
    Resource,
    ResourceType,
    SourceReference,
    StudentProfile,
    TaskState,
    TaskStatus,
)


class _MockProfileAgent:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def extract(self, request, previous):
        from app.schemas import ProfileChatResponse

        self.calls.append((request.student_id, previous.version if previous else 0))
        new_version = (previous.version + 1) if previous else 1
        new_profile = previous.model_copy(deep=True)
        new_profile.version = new_version
        return ProfileChatResponse(
            profile=new_profile,
            missing_dimensions=[],
            next_question=None,
            is_complete=True,
            extraction_mode="development_heuristic",
        )


class _MockPlannerAgent:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def generate(
        self,
        profile: StudentProfile,
        previous_path: LearningPath | None = None,
        previous_path_id: str | None = None,
        evaluation_summary: str | None = None,
        target_topics: list[str] | None = None,
    ) -> LearningPath:
        self.calls.append(profile.student_id)
        return LearningPath(
            path_id=str(uuid4()),
            student_id=profile.student_id,
            profile_version=profile.version,
            course=profile.course.value or "机器学习基础",
            steps=[
                LearningPathStep(
                    step=1,
                    topic="重学薄弱知识点",
                    learning_goal="巩固薄弱环节",
                    reason="基于评价反馈调整",
                    recommended_resources=["explanation"],
                    completion_criteria=["通过再次评价"],
                    estimated_minutes=30,
                    prerequisites=[],
                )
            ],
            adjustment_reason="基于评价结果调整",
            generation_mode="development_rule_based",
            created_at="2026-07-15T10:00:00Z",
        )


@pytest.fixture
def repository(tmp_path: Path) -> Repository:
    database = SQLiteDatabase(tmp_path / "evaluation-service.db")
    database.initialize()
    return Repository(database)


def _learning_path(student_id: str, path_id: str = "path-1") -> LearningPath:
    return LearningPath(
        path_id=path_id,
        student_id=student_id,
        profile_version=1,
        course="机器学习",
        steps=[
            LearningPathStep(
                step=1,
                topic="机器学习概述",
                learning_goal="了解基本概念",
                reason="入门",
                recommended_resources=["explanation"],
                completion_criteria=["通过"],
                estimated_minutes=30,
                prerequisites=[],
            )
        ],
        adjustment_reason=None,
        generation_mode="development_rule_based",
        created_at="2026-07-15T08:00:00Z",
    )


def _save_quiz(
    repository: Repository,
    *,
    student_id: str,
    topic: str = "机器学习概述",
) -> str:
    task_id = str(uuid4())
    resource_id = str(uuid4())
    question_id = f"{resource_id}::q1"
    repository.save_task(
        TaskState(
            task_id=task_id,
            task_type="resource_generation",
            student_id=student_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            current_stage="completed",
        )
    )
    repository.save_resource(
        Resource(
            resource_id=resource_id,
            resource_type=ResourceType.QUIZ,
            title=f"{topic} 测验",
            content=json.dumps(
                {
                    "topic": topic,
                    "questions": [
                        {
                            "id": question_id,
                            "type": "single_choice",
                            "level": "basic",
                            "question": "机器学习的主要任务是什么？",
                            "options": ["A. 从数据中学习规律", "B. 仅存储数据"],
                            "answer": "A",
                            "explanation": "机器学习从数据中学习可泛化的规律。",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            content_format="json",
            target_topic=topic,
            difficulty=Difficulty.BEGINNER,
            personalization_reason="依据当前学习路径步骤生成真实评价题目",
            source_references=[
                SourceReference(
                    source_id="ml-overview",
                    title="机器学习基础",
                    locator="data/machine_learning/01-overview.md",
                )
            ],
            review_status="approved",
        ),
        task_id=task_id,
    )
    return question_id


@pytest.fixture
def base_profile() -> StudentProfile:
    from app.schemas.profile import FieldEvidence, ProfileField, TimeBudget

    return StudentProfile(
        student_id="stu-test-1",
        version=1,
        major=ProfileField(
            value="计算机",
            evidence=[FieldEvidence(source="conversation", quote="我学计算机")],
            confidence=0.8,
        ),
        course=ProfileField(
            value="机器学习",
            evidence=[FieldEvidence(source="conversation", quote="学机器学习")],
            confidence=0.8,
        ),
        knowledge_level=ProfileField(value="beginner", evidence=[], confidence=0.7),
        learning_goals=ProfileField(value=["掌握机器学习"], evidence=[], confidence=0.7),
        weak_topics=ProfileField(value=["梯度下降"], evidence=[], confidence=0.7),
        learning_history=ProfileField(value=[], evidence=[], confidence=0.0),
        cognitive_style=ProfileField(value="practice_oriented", evidence=[], confidence=0.6),
        language_preference=ProfileField(value="中文", evidence=[], confidence=0.7),
        resource_preference=ProfileField(value=[], evidence=[], confidence=0.0),
        time_budget=ProfileField(
            value=TimeBudget(minutes_per_day=45, days_per_week=5),
            evidence=[],
            confidence=0.7,
        ),
        evidence=[],
        confidence=0.7,
        updated_at="2026-07-15T09:00:00Z",
    )


def test_evaluation_with_failing_score_triggers_updates(base_profile, repository):
    repo = repository
    repo.save_profile(base_profile)
    repo.save_path(_learning_path(base_profile.student_id))
    question_id = _save_quiz(repo, student_id=base_profile.student_id)

    profile_agent = _MockProfileAgent()
    planner_agent = _MockPlannerAgent()

    service = EvaluationService(
        evaluator=EvaluationAgent(),
        profile_agent=profile_agent,
        planner_agent=planner_agent,
        repository=repo,
    )

    submission = EvaluationSubmission(
        student_id=base_profile.student_id,
        path_id="path-1",
        step=1,
        answers=[{"question_id": question_id, "response": "B"}],
        time_spent_minutes=15,
    )

    result_model = asyncio.run(service.process(submission))

    assert result_model.result.passed is False
    assert result_model.result.profile_update_required is True
    assert result_model.result.path_update_required is True
    assert len(profile_agent.calls) == 1
    assert len(planner_agent.calls) == 1
    assert result_model.updated_profile is not None
    assert result_model.updated_path is not None
    assert repo.get_latest_profile(base_profile.student_id).version == 2


def test_evaluation_with_passing_score_skips_updates(base_profile, repository):
    repo = repository
    repo.save_profile(base_profile)
    repo.save_path(_learning_path(base_profile.student_id))
    question_id = _save_quiz(repo, student_id=base_profile.student_id)

    profile_agent = _MockProfileAgent()
    planner_agent = _MockPlannerAgent()

    service = EvaluationService(
        evaluator=EvaluationAgent(),
        profile_agent=profile_agent,
        planner_agent=planner_agent,
        repository=repo,
    )

    submission = EvaluationSubmission(
        student_id=base_profile.student_id,
        path_id="path-1",
        step=1,
        answers=[
            {
                "question_id": question_id,
                "response": "A",
            },
        ],
        time_spent_minutes=20,
    )

    result_model = asyncio.run(service.process(submission))

    assert result_model.updated_profile is None
    assert result_model.updated_path is None
    assert len(profile_agent.calls) == 0
    assert len(planner_agent.calls) == 0


def test_evaluation_handles_missing_profile_gracefully(repository):
    repo = repository
    student_id = "nonexistent-student"
    repo.save_path(_learning_path(student_id, path_id="path-x"))
    question_id = _save_quiz(repo, student_id=student_id)
    profile_agent = _MockProfileAgent()
    planner_agent = _MockPlannerAgent()

    service = EvaluationService(
        evaluator=EvaluationAgent(),
        profile_agent=profile_agent,
        planner_agent=planner_agent,
        repository=repo,
    )

    submission = EvaluationSubmission(
        student_id=student_id,
        path_id="path-x",
        step=1,
        answers=[{"question_id": question_id, "response": "B"}],
        time_spent_minutes=10,
    )

    result_model = asyncio.run(service.process(submission))

    assert result_model.result is not None
    assert result_model.updated_profile is None
    assert result_model.updated_path is None


def test_evaluator_without_repository_fails_with_configuration_error():
    submission = EvaluationSubmission(
        student_id="stu-test-1",
        path_id="path-1",
        step=1,
        answers=[{"question_id": "resource-id::q1", "response": "A"}],
        time_spent_minutes=5,
    )

    with pytest.raises(EvaluationConfigurationError, match="repository is not configured"):
        asyncio.run(
            EvaluationAgent().evaluate(
                submission,
                expected_topic="机器学习概述",
            )
        )
