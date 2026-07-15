from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


TEST_STUDENT_TEXT = """我是人工智能专业的学生，刚开始学习机器学习，数学基础比较一般。
我想理解支持向量机，并且最后能使用Python完成一个简单分类项目。
我比较喜欢图示、生活中的类比和代码案例，每天大概能学习30分钟。"""


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        host="127.0.0.1",
        port=8000,
        database_path=tmp_path / "eduagent-test.db",
        allowed_origins=("http://localhost:5173",),
        profile_mode="development_heuristic",
        planner_mode="development_rule_based",
    )


@pytest.fixture
def test_app(settings: Settings):
    return create_app(settings)


@pytest.fixture
def client(test_app):
    with TestClient(test_app) as test_client:
        yield test_client


@pytest.fixture
def profile_payload() -> dict:
    return {
        "student_id": "contract-student",
        "conversation_id": "contract-conversation",
        "messages": [
            {
                "message_id": "contract-message-1",
                "role": "user",
                "content": TEST_STUDENT_TEXT,
            }
        ],
        "evaluation_summary": None,
    }


@pytest.fixture
def saved_profile(client: TestClient, profile_payload: dict) -> dict:
    response = client.post("/api/profile/chat", json=profile_payload)
    assert response.status_code == 200
    return response.json()["profile"]


@pytest.fixture
def saved_path(client: TestClient, saved_profile: dict) -> dict:
    response = client.post(
        "/api/path/generate",
        json={"student_id": saved_profile["student_id"]},
    )
    assert response.status_code == 200
    return response.json()["path"]
