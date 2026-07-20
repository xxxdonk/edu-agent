from __future__ import annotations

import asyncio
import json
import time
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


def test_unknown_course_never_falls_back_to_machine_learning(client: TestClient) -> None:
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
    assert course["value"] != "机器学习基础"
    assert all(evidence["source"] != "system_default" for evidence in course["evidence"])


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


def test_resources_generate_and_evaluation_with_agent2(
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
    # Poll until task completes (background task runs asynchronously)
    import time as _time
    for _ in range(30):
        task_response = client.get(accepted_body["status_url"])
        task = task_response.json()
        if task["status"] in ("completed", "partial_success", "failed"):
            break
        _time.sleep(0.5)
    assert task["status"] == "completed", f"task failed: {task.get('errors', [])}"
    assert len(task["result_resource_ids"]) == 5
    # Each resource should be retrievable and have source_references
    resources: dict[str, dict] = {}
    for resource_id in task["result_resource_ids"]:
        res = client.get(f"/api/resources/{resource_id}")
        assert res.status_code == 200
        resource = res.json()
        resources[resource["resource_type"]] = resource
        assert len(resource["source_references"]) >= 1
        assert resource["review_status"] == "approved"

    events = client.get(accepted_body["events_url"])
    assert events.status_code == 200
    assert events.headers["content-type"].startswith("text/event-stream")
    assert "event: agent" in events.text
    business_events = [
        json.loads(line.removeprefix("data: "))
        for line in events.text.splitlines()
        if line.startswith("data: ")
    ]
    sequences = [event["sequence"] for event in business_events]
    assert sequences == list(range(1, len(sequences) + 1))
    assert len(sequences) == len(set(sequences))
    assert any(
        event["agent"] == "retriever_agent" and event["status"] == "started"
        for event in business_events
    )
    assert any(
        event["agent"] == "retriever_agent" and event["status"] == "completed"
        for event in business_events
    )
    terminal_event = business_events[-1]
    assert terminal_event["event_type"] == "task"
    assert terminal_event["status"] == task["status"]

    resume_after = sequences[len(sequences) // 2]
    resumed = client.get(
        accepted_body["events_url"],
        params={"after": resume_after - 1},
        headers={"Last-Event-ID": str(resume_after)},
    )
    resumed_events = [
        json.loads(line.removeprefix("data: "))
        for line in resumed.text.splitlines()
        if line.startswith("data: ")
    ]
    assert resumed_events
    assert all(event["sequence"] > resume_after for event in resumed_events)
    assert resumed_events[-1]["status"] == task["status"]

    quiz = json.loads(resources["quiz"]["content"])
    first_question = quiz["questions"][0]
    evaluation = client.post(
        "/api/evaluation/submit",
        json={
            "student_id": saved_profile["student_id"],
            "path_id": saved_path["path_id"],
            "step": 1,
            "answers": [
                {
                    "question_id": first_question["id"],
                    "response": "这是一段很长但与题目和标准答案完全无关的错误回答。" * 6,
                }
            ],
            "time_spent_minutes": 5,
        },
    )
    assert evaluation.status_code == 200
    eval_body = evaluation.json()
    assert "mastery_score" in eval_body
    assert eval_body["passed"] is False
    assert eval_body["weak_topics"]
    assert eval_body["profile_update_suggestions"]["evidence_source"] == "evaluation"
    assert eval_body["profile_update_suggestions"]["updated_profile_version"] == saved_profile["version"] + 1
    updated_path = eval_body["path_update_suggestions"]["updated_path"]
    assert updated_path["profile_version"] == saved_profile["version"] + 1
    assert updated_path["adjustment_reason"]

    latest_profile = client.get(f"/api/profile/{saved_profile['student_id']}")
    assert latest_profile.status_code == 200
    assert latest_profile.json()["version"] == saved_profile["version"] + 1
    assert any(
        evidence["source"] == "evaluation"
        for evidence in latest_profile.json()["weak_topics"]["evidence"]
    )


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


class _RejectingReviewer:
    agent_name = "test_reviewer_agent"

    async def review(self, resource: Resource, context) -> Resource:
        return resource.model_copy(update={"review_status": "rejected"})


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

        failed = client.post(
            "/api/resources/generate",
            json={
                "student_id": profile["student_id"],
                "path_id": path["path_id"],
                "step": 1,
                "resource_types": ["quiz"],
            },
        ).json()
        failed_task = client.get(failed["status_url"]).json()
        assert failed_task["status"] == "failed"
        assert failed_task["result_resource_ids"] == []


def test_reviewer_rejection_never_publishes_resource_as_success(settings: Settings) -> None:
    app = create_app(settings)
    generation_log: list[str] = []
    app.state.agent_registry.register_resource(
        _SuccessfulResourceAgent(ResourceType.EXPLANATION, generation_log)
    )
    app.state.agent_registry.register_reviewer(_RejectingReviewer())

    with TestClient(app) as client:
        profile = client.post(
            "/api/profile/chat",
            json={
                "student_id": "rejected-review-student",
                "messages": [
                    {
                        "role": "user",
                        "content": "我是人工智能专业学生，正在学习机器学习，梯度下降不懂，希望完成分类项目，每天45分钟，喜欢代码和图示。",
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
                "resource_types": ["explanation"],
            },
        ).json()
        task = client.get(accepted["status_url"]).json()

        assert task["status"] == "failed"
        assert task["result_resource_ids"] == []
        assert any("review explanation:rejected" in error for error in task["errors"])


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
