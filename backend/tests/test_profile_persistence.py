from __future__ import annotations

import asyncio
import logging
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app.database import Repository, SQLiteDatabase
from app.database.repositories import safe_student_reference
from app.evaluation import EvaluationService
from app.profile import DevelopmentProfileAgent
from app.schemas import (
    EvaluationResult,
    EvaluationSubmission,
    ProfileChatRequest,
    ProfileChatResponse,
    StudentProfile,
)
from app.schemas.profile import ChatMessage


VERSION_CONFLICT = (
    "UNIQUE constraint failed: profiles.student_id, profiles.version"
)


def _profile(
    student_id: str,
    topic: str,
    *,
    proposed_version: int = 1,
) -> StudentProfile:
    request = ProfileChatRequest(
        student_id=student_id,
        messages=[
            ChatMessage(
                message_id=f"message-{topic}",
                role="user",
                content=(
                    "我是人工智能专业学生，正在学习机器学习，每天学习45分钟，"
                    f"需要加强：{topic}，希望通过代码实践掌握分类模型。"
                ),
            )
        ],
    )
    profile = DevelopmentProfileAgent().extract(request, None).profile
    return profile.model_copy(
        deep=True,
        update={"version": proposed_version},
    )


def _repository(tmp_path: Path) -> Repository:
    database = SQLiteDatabase(tmp_path / "profile-persistence.db")
    database.initialize()
    return Repository(database)


def _stored_versions(repository: Repository, student_id: str) -> list[int]:
    with repository.database.connect() as connection:
        rows = connection.execute(
            "SELECT version FROM profiles WHERE student_id = ? ORDER BY version",
            (student_id,),
        ).fetchall()
    return [int(row["version"]) for row in rows]


def _save_concurrently(
    repository: Repository,
    profiles: list[StudentProfile],
) -> list[StudentProfile]:
    barrier = threading.Barrier(len(profiles))

    def save(profile: StudentProfile) -> StudentProfile:
        barrier.wait(timeout=5)
        return repository.save_profile(profile)

    with ThreadPoolExecutor(max_workers=len(profiles)) as executor:
        futures = [executor.submit(save, profile) for profile in profiles]
        return [future.result(timeout=15) for future in futures]


def test_profile_versions_start_at_one_and_increment_sequentially(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    student_id = "sequential-profile-student"

    first = repository.save_profile(
        _profile(student_id, "梯度下降", proposed_version=99)
    )
    second = repository.save_profile(
        _profile(student_id, "逻辑回归", proposed_version=1)
    )

    assert (first.version, second.version) == (1, 2)
    assert _stored_versions(repository, student_id) == [1, 2]
    assert repository.get_latest_profile(student_id) == second


def test_concurrent_stale_updates_receive_distinct_contiguous_versions(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    student_id = "concurrent-profile-student"
    repository.save_profile(_profile(student_id, "数学基础"))
    stale_updates = [
        _profile(student_id, "梯度下降", proposed_version=2),
        _profile(student_id, "模型评估", proposed_version=2),
    ]

    persisted = _save_concurrently(repository, stale_updates)

    assert {profile.version for profile in persisted} == {2, 3}
    assert _stored_versions(repository, student_id) == [1, 2, 3]
    assert repository.get_latest_profile(student_id).version == 3


def test_concurrent_duplicate_content_is_persisted_once(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    student_id = "duplicate-profile-student"
    repository.save_profile(_profile(student_id, "数学基础"))
    duplicate = _profile(student_id, "梯度下降", proposed_version=2)

    persisted = _save_concurrently(
        repository,
        [duplicate, duplicate.model_copy(deep=True)],
    )

    assert [profile.version for profile in persisted] == [2, 2]
    assert _stored_versions(repository, student_id) == [1, 2]


class _BoundEvaluator:
    def bind_repository(self, repository: Repository) -> None:
        self.repository = repository


class _UnusedPlanner:
    pass


class _BarrierEvaluationProfileAgent:
    def __init__(self, barrier: threading.Barrier) -> None:
        self._barrier = barrier

    async def extract(self, request, previous):
        self._barrier.wait(timeout=5)
        return ProfileChatResponse(
            profile=_profile(
                request.student_id,
                "评价后的模型评估薄弱点",
                proposed_version=previous.version + 1,
            ),
            missing_dimensions=[],
            next_question=None,
            is_complete=True,
            extraction_mode="development_heuristic",
        )


def test_evaluation_update_and_profile_chat_allocate_versions_safely(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    student_id = "evaluation-chat-concurrent-student"
    repository.save_profile(_profile(student_id, "数学基础"))
    barrier = threading.Barrier(2)
    service = EvaluationService(
        evaluator=_BoundEvaluator(),
        profile_agent=_BarrierEvaluationProfileAgent(barrier),
        planner_agent=_UnusedPlanner(),
        repository=repository,
    )
    submission = EvaluationSubmission(
        student_id=student_id,
        path_id="path-not-needed-for-profile-update",
        step=1,
        answers=[{"question_id": "q1", "response": "B"}],
        time_spent_minutes=10,
    )
    result = EvaluationResult(
        evaluation_id="evaluation-concurrency",
        student_id=student_id,
        path_id=submission.path_id,
        step=1,
        mastery_score=0.4,
        passed=False,
        weak_topics=["模型评估"],
        feedback="需要加强模型评估。",
        profile_update_required=True,
        path_update_required=True,
    )

    def save_evaluation() -> StudentProfile | None:
        return asyncio.run(
            service._trigger_profile_update(submission, result, {})
        )

    def save_chat() -> StudentProfile:
        barrier.wait(timeout=5)
        return repository.save_profile(
            _profile(student_id, "逻辑回归", proposed_version=2)
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        evaluation_future = executor.submit(save_evaluation)
        chat_future = executor.submit(save_chat)
        persisted = [
            evaluation_future.result(timeout=15),
            chat_future.result(timeout=15),
        ]

    assert all(profile is not None for profile in persisted)
    assert {profile.version for profile in persisted if profile is not None} == {2, 3}
    assert _stored_versions(repository, student_id) == [1, 2, 3]


class _InsertFailureConnection:
    def __init__(
        self,
        connection: sqlite3.Connection,
        failure: sqlite3.IntegrityError,
        remaining_failures: list[int],
        *,
        insert_before_failure: bool,
    ) -> None:
        self._connection = connection
        self._failure = failure
        self._remaining_failures = remaining_failures
        self._insert_before_failure = insert_before_failure

    def execute(self, statement: str, parameters=()):
        is_profile_insert = statement.lstrip().startswith("INSERT INTO profiles")
        if is_profile_insert and self._remaining_failures[0] > 0:
            self._remaining_failures[0] -= 1
            if self._insert_before_failure:
                self._connection.execute(statement, parameters)
            raise self._failure
        return self._connection.execute(statement, parameters)


def _inject_insert_failures(
    database: SQLiteDatabase,
    monkeypatch: pytest.MonkeyPatch,
    error: sqlite3.IntegrityError,
    count: int,
    *,
    insert_before_failure: bool = False,
) -> list[int]:
    original_connect = database.connect
    remaining = [count]

    @contextmanager
    def connect() -> Iterator[_InsertFailureConnection]:
        with original_connect() as connection:
            yield _InsertFailureConnection(
                connection,
                error,
                remaining,
                insert_before_failure=insert_before_failure,
            )

    monkeypatch.setattr(database, "connect", connect)
    return remaining


def test_profile_version_conflict_rolls_back_and_retries_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository = _repository(tmp_path)
    student_id = "retry-profile-student"
    caplog.set_level(logging.INFO)
    _inject_insert_failures(
        repository.database,
        monkeypatch,
        sqlite3.IntegrityError(VERSION_CONFLICT),
        1,
        insert_before_failure=True,
    )

    persisted = repository.save_profile(_profile(student_id, "梯度下降"))

    assert persisted.version == 1
    assert _stored_versions(repository, student_id) == [1]
    assert "profile_version_conflict" in caplog.text
    assert "profile_version_retry" in caplog.text
    assert student_id not in caplog.text
    assert safe_student_reference(student_id) in caplog.text


def test_profile_version_conflict_retry_is_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    remaining = _inject_insert_failures(
        repository.database,
        monkeypatch,
        sqlite3.IntegrityError(VERSION_CONFLICT),
        2,
    )

    with pytest.raises(sqlite3.IntegrityError, match="profiles.student_id"):
        repository.save_profile(_profile("bounded-retry-student", "梯度下降"))

    assert remaining == [0]
    assert _stored_versions(repository, "bounded-retry-student") == []


def test_unrelated_integrity_error_is_not_swallowed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    _inject_insert_failures(
        repository.database,
        monkeypatch,
        sqlite3.IntegrityError(
            "NOT NULL constraint failed: profiles.profile_json"
        ),
        1,
    )

    with pytest.raises(sqlite3.IntegrityError, match="profile_json"):
        repository.save_profile(_profile("integrity-student", "梯度下降"))

    assert _stored_versions(repository, "integrity-student") == []


class _StaleVersionProfileAgent:
    async def extract(self, request, previous):
        profile = _profile(request.student_id, "逻辑回归", proposed_version=99)
        return ProfileChatResponse(
            profile=profile,
            missing_dimensions=[],
            next_question=None,
            is_complete=True,
            extraction_mode="development_heuristic",
        )


def test_profile_chat_returns_the_version_actually_persisted(
    client: TestClient,
    test_app,
) -> None:
    test_app.state.profile_agent = _StaleVersionProfileAgent()
    student_id = "api-version-student"
    response = client.post(
        "/api/profile/chat",
        json={
            "student_id": student_id,
            "messages": [
                {
                    "message_id": "api-version-message",
                    "role": "user",
                    "content": "请更新我的机器学习画像。",
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["profile"]["version"] == 1
    stored = client.get(f"/api/profile/{student_id}")
    assert stored.status_code == 200
    assert stored.json() == response.json()["profile"]


def test_profile_persistence_failure_cannot_return_false_success(
    test_app,
    monkeypatch: pytest.MonkeyPatch,
    profile_payload: dict,
) -> None:
    def fail(_: StudentProfile) -> StudentProfile:
        raise sqlite3.IntegrityError(
            "NOT NULL constraint failed: profiles.profile_json"
        )

    monkeypatch.setattr(test_app.state.repository, "save_profile", fail)
    with TestClient(test_app, raise_server_exceptions=False) as client:
        response = client.post("/api/profile/chat", json=profile_payload)

    assert response.status_code == 500
