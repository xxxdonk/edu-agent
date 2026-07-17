from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.schemas import Resource, ResourceType, SourceReference
from app.schemas.common import Difficulty


PROFILE_FIELDS = (
    "major",
    "course",
    "knowledge_level",
    "learning_goals",
    "weak_topics",
    "learning_history",
    "cognitive_style",
    "language_preference",
    "resource_preference",
    "time_budget",
)


def test_health_returns_200(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "ok"


def test_profile_contract_evidence_and_persistence(
    client: TestClient,
    profile_payload: dict,
) -> None:
    response = client.post("/api/profile/chat", json=profile_payload)
    assert response.status_code == 200
    body = response.json()
    profile = body["profile"]

    valid_dimensions = sum(
        1
        for name in PROFILE_FIELDS
        if profile[name]["value"] not in (None, []) and profile[name]["confidence"] > 0
    )
    assert valid_dimensions >= 6
    for name in PROFILE_FIELDS:
        assert set(profile[name]) == {"value", "evidence", "confidence"}

    direct_fields = ("major", "course", "learning_goals", "weak_topics", "time_budget")
    for name in direct_fields:
        conversation_evidence = [
            item for item in profile[name]["evidence"] if item["source"] == "conversation"
        ]
        assert conversation_evidence
        assert conversation_evidence[0]["message_id"] == "contract-message-1"
        assert conversation_evidence[0]["quote"] == profile_payload["messages"][0]["content"][:500]

    assert profile["knowledge_level"]["evidence"][0]["source"] == "inference"
    assert profile["cognitive_style"]["evidence"][0]["source"] == "inference"
    assert profile["knowledge_level"]["confidence"] < profile["major"]["confidence"]
    assert any(
        item["source"] == "system_default"
        for item in profile["time_budget"]["evidence"]
    )

    top_level_keys = {
        (item["source"], item["quote"], item["message_id"])
        for item in profile["evidence"]
    }
    for name in PROFILE_FIELDS:
        for item in profile[name]["evidence"]:
            assert (item["source"], item["quote"], item["message_id"]) in top_level_keys

    expected_overall = round(
        sum(profile[name]["confidence"] for name in PROFILE_FIELDS) / len(PROFILE_FIELDS),
        3,
    )
    assert profile["confidence"] == expected_overall

    stored = client.get(f"/api/profile/{profile['student_id']}")
    assert stored.status_code == 200
    assert stored.json() == profile


def test_system_default_course_has_explicit_evidence(client: TestClient) -> None:
    response = client.post(
        "/api/profile/chat",
        json={
            "student_id": "default-course-student",
            "messages": [
                {
                    "message_id": "default-course-message",
                    "role": "user",
                    "content": "我是人工智能专业学生，零基础，想理解分类算法，喜欢图示，每天30分钟。",
                }
            ],
        },
    )
    assert response.status_code == 200
    course = response.json()["profile"]["course"]
    assert course["value"] == "机器学习基础"
    assert course["confidence"] < 0.78
    assert course["evidence"][0]["source"] == "system_default"


def test_missing_profile_returns_404(client: TestClient) -> None:
    response = client.get("/api/profile/not-found")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROFILE_NOT_FOUND"


def test_learning_path_is_ordered_and_complete(saved_path: dict) -> None:
    steps = saved_path["steps"]
    assert [item["step"] for item in steps] == list(range(1, len(steps) + 1))
    assert [item["topic"] for item in steps] == [
        "数学基础",
        "支持向量机",
        "Python简单分类项目",
    ]
    required = {
        "step",
        "topic",
        "learning_goal",
        "reason",
        "recommended_resources",
        "completion_criteria",
        "estimated_minutes",
        "prerequisites",
    }
    for item in steps:
        assert set(item) == required
        assert item["recommended_resources"]
        assert item["completion_criteria"]
        assert item["estimated_minutes"] > 0


def test_unregistered_resources_fail_without_fake_results_and_sse_works(
    client: TestClient,
    saved_profile: dict,
    saved_path: dict,
) -> None:
    accepted = client.post(
        "/api/resources/generate",
        json={
            "student_id": saved_profile["student_id"],
            "path_id": saved_path["path_id"],
            "step": 1,
        },
    )
    assert accepted.status_code == 202
    accepted_body = accepted.json()
    assert accepted_body["task_id"]

    task_response = client.get(accepted_body["status_url"])
    assert task_response.status_code == 200
    task = task_response.json()
    assert task["status"] == "failed"
    assert task["result_resource_ids"] == []
    assert len(task["errors"]) == 5
    assert all("尚未注册" in error for error in task["errors"])

    events = client.get(accepted_body["events_url"])
    assert events.status_code == 200
    assert events.headers["content-type"].startswith("text/event-stream")
    assert "event: agent" in events.text
    assert '"status": "failed"' in events.text

    evaluation = client.post(
        "/api/evaluation/submit",
        json={
            "student_id": saved_profile["student_id"],
            "path_id": saved_path["path_id"],
            "step": 1,
            "answers": [{"question_id": "q-1", "response": "answer"}],
            "time_spent_minutes": 5,
        },
    )
    assert evaluation.status_code == 501
    assert evaluation.json()["error"]["details"]["mock"] is True


class _SuccessfulResourceAgent:
    def __init__(self, resource_type: ResourceType, generation_log: list[str]) -> None:
        self.resource_type = resource_type
        self.agent_name = f"test_{resource_type.value}_agent"
        self.generation_log = generation_log

    async def generate(self, context) -> Resource:
        await asyncio.sleep(0.01)
        self.generation_log.append(self.resource_type.value)
        topic = next(
            item.topic for item in context.path.steps if item.step == context.request.step
        )
        return Resource(
            resource_id=str(uuid4()),
            resource_type=self.resource_type,
            title=f"{topic} test resource",
            content="validated test content",
            content_format=(
                "mermaid" if self.resource_type == ResourceType.MIND_MAP else "markdown"
            ),
            target_topic=topic,
            difficulty=context.profile.knowledge_level.value or Difficulty.BEGINNER,
            personalization_reason="generated from profile and path context",
            source_references=[
                SourceReference(
                    source_id="test-source",
                    title="Test source",
                    locator="test://source",
                )
            ],
            review_status="pending",
        )


class _FailingResourceAgent:
    resource_type = ResourceType.QUIZ
    agent_name = "test_quiz_agent"

    def __init__(self, generation_log: list[str]) -> None:
        self.generation_log = generation_log

    async def generate(self, context) -> Resource:
        await asyncio.sleep(0.005)
        self.generation_log.append(self.resource_type.value)
        raise RuntimeError("isolated quiz failure")


class _TrackingReviewer:
    agent_name = "test_reviewer_agent"

    def __init__(self, generation_log: list[str], reviewed: list[str]) -> None:
        self.generation_log = generation_log
        self.reviewed = reviewed

    async def review(self, resource: Resource, context) -> Resource:
        assert set(self.generation_log) == {"explanation", "mind_map", "quiz"}
        self.reviewed.append(resource.resource_id)
        return resource.model_copy(update={"review_status": "approved"})


def test_reviewer_runs_for_every_success_after_partial_generation(settings: Settings) -> None:
    app = create_app(settings)
    generation_log: list[str] = []
    reviewed: list[str] = []
    registry = app.state.agent_registry
    registry.register_resource(
        _SuccessfulResourceAgent(ResourceType.EXPLANATION, generation_log)
    )
    registry.register_resource(
        _SuccessfulResourceAgent(ResourceType.MIND_MAP, generation_log)
    )
    registry.register_resource(_FailingResourceAgent(generation_log))
    registry.register_reviewer(_TrackingReviewer(generation_log, reviewed))

    with TestClient(app) as client:
        profile = client.post(
            "/api/profile/chat",
            json={
                "student_id": "review-student",
                "messages": [
                    {
                        "role": "user",
                        "content": "我是人工智能专业学生，刚开始学习机器学习，数学基础比较一般。我想理解支持向量机，喜欢图示和代码案例，每天30分钟。",
                    }
                ],
            },
        ).json()["profile"]
        path = client.post(
            "/api/path/generate", json={"student_id": profile["student_id"]}
        ).json()["path"]
        accepted = client.post(
            "/api/resources/generate",
            json={
                "student_id": profile["student_id"],
                "path_id": path["path_id"],
                "step": 1,
                "resource_types": ["explanation", "mind_map", "quiz"],
            },
        ).json()
        task = client.get(accepted["status_url"]).json()
        assert task["status"] == "partial_success"
        assert len(task["result_resource_ids"]) == 2
        assert set(reviewed) == set(task["result_resource_ids"])
        for resource_id in task["result_resource_ids"]:
            resource = client.get(f"/api/resources/{resource_id}").json()
            assert resource["review_status"] == "approved"

        completed = client.post(
            "/api/resources/generate",
            json={
                "student_id": profile["student_id"],
                "path_id": path["path_id"],
                "step": 1,
                "resource_types": ["explanation", "mind_map"],
            },
        ).json()
        completed_task = client.get(completed["status_url"]).json()
        assert completed_task["status"] == "completed"
        assert len(completed_task["result_resource_ids"]) == 2


def test_default_sqlite_path_is_independent_of_working_directory(
    monkeypatch,
) -> None:
    project_root = Path(__file__).resolve().parents[2]
    backend_directory = project_root / "backend"
    monkeypatch.delenv("DATABASE_URL", raising=False)

    monkeypatch.chdir(project_root)
    from_root = Settings.from_env().database_path
    monkeypatch.chdir(backend_directory)
    from_backend = Settings.from_env().database_path

    assert from_root == from_backend
    assert from_root == (project_root / "data" / "eduagent.db").resolve()
