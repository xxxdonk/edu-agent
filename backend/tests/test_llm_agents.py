from __future__ import annotations

import asyncio

import pytest

from app.llm import (
    FakeLLMClient,
    LLMConfigurationError,
    LLMTimeoutError,
)
from app.llm.openai_compatible import OpenAICompatibleLLMClient
from app.planner import PlannerAgent
from app.profile import DevelopmentProfileAgent, ProfileAgent
from app.schemas import ProfileChatRequest, ResourceType
from app.schemas.profile import ChatMessage

from conftest import TEST_STUDENT_TEXT


def _evidence(source: str, quote: str, message_id: str | None = "message-a") -> dict:
    return {"source": source, "quote": quote, "message_id": message_id}


def _scalar(value, evidence: list[dict] | None = None, confidence: float = 0.0) -> dict:
    return {"value": value, "evidence": evidence or [], "confidence": confidence}


def _list(value: list[str], evidence: list[dict] | None = None, confidence: float = 0.0) -> dict:
    return {"value": value, "evidence": evidence or [], "confidence": confidence}


def _complete_profile_draft(message_id: str = "message-a") -> dict:
    return {
        "major": _scalar(
            "人工智能",
            [_evidence("conversation", "人工智能专业", message_id)],
            0.92,
        ),
        "course": _scalar(
            "机器学习",
            [_evidence("conversation", "学习机器学习", message_id)],
            0.9,
        ),
        "knowledge_level": _scalar(
            "beginner",
            [_evidence("inference", "刚开始学习机器学习", message_id)],
            0.85,
        ),
        "learning_goals": _list(
            ["理解支持向量机", "使用Python完成简单分类项目"],
            [_evidence("conversation", "我想理解支持向量机", message_id)],
            0.88,
        ),
        "weak_topics": _list(
            ["数学基础"],
            [_evidence("conversation", "数学基础比较一般", message_id)],
            0.86,
        ),
        "learning_history": _list([], [], 0.0),
        "cognitive_style": _scalar(
            "visual",
            [_evidence("inference", "喜欢图示", message_id)],
            0.8,
        ),
        "language_preference": _scalar(None, [], 0.0),
        "resource_preference": _list(
            ["思维导图", "代码实践案例"],
            [_evidence("inference", "代码案例", message_id)],
            0.8,
        ),
        "time_budget": _scalar(
            {"minutes_per_day": 30, "days_per_week": 5},
            [
                _evidence(
                    "conversation", "每天大概能学习30分钟", message_id
                ),
                _evidence(
                    "system_default", "未提供每周学习天数，默认5天", None
                ),
            ],
            0.7,
        ),
        "next_question": None,
    }


def _complete_request(student_id: str = "llm-student") -> ProfileChatRequest:
    return ProfileChatRequest(
        student_id=student_id,
        conversation_id="conversation-a",
        messages=[
            ChatMessage(
                message_id="message-a",
                role="user",
                content=TEST_STUDENT_TEXT,
            )
        ],
    )


def _development_profile(student_id: str = "planner-student"):
    return DevelopmentProfileAgent().extract(_complete_request(student_id), None).profile


def _path_draft() -> dict:
    resources = [
        ResourceType.EXPLANATION.value,
        ResourceType.MIND_MAP.value,
        ResourceType.CODING.value,
    ]
    return {
        "steps": [
            {
                "step": 1,
                "topic": "数学基础",
                "learning_goal": "补足支持向量机所需的数学基础",
                "reason": "画像显示数学基础是薄弱点，因此优先补足",
                "recommended_resources": resources,
                "completion_criteria": ["能解释向量和内积", "练习正确率达到80%"],
                "estimated_minutes": 30,
                "prerequisites": [],
            },
            {
                "step": 2,
                "topic": "支持向量机",
                "learning_goal": "理解分类间隔、支持向量和核方法的基本作用",
                "reason": "直接服务于学生希望理解支持向量机的目标",
                "recommended_resources": resources,
                "completion_criteria": ["能用图示解释最大间隔", "完成基础练习"],
                "estimated_minutes": 30,
                "prerequisites": ["数学基础"],
            },
            {
                "step": 3,
                "topic": "Python简单分类项目",
                "learning_goal": "使用Python完成一个简单分类项目",
                "reason": "结合学生的代码案例偏好和实践目标",
                "recommended_resources": ["coding", "quiz"],
                "completion_criteria": ["代码可运行", "能解释模型结果"],
                "estimated_minutes": 30,
                "prerequisites": ["支持向量机"],
            },
        ],
        "total_estimated_minutes": 90,
        "adjustment_reason": None,
    }


def test_fake_llm_profile_success_and_evidence_classification() -> None:
    fake = FakeLLMClient([_complete_profile_draft()])
    response = asyncio.run(
        ProfileAgent(fake, enable_llm=True).extract(_complete_request(), None)
    )

    assert response.extraction_mode == "llm_structured"
    assert response.is_complete is True
    assert response.profile.major.evidence[0].source == "conversation"
    assert response.profile.knowledge_level.evidence[0].source == "inference"
    assert response.profile.knowledge_level.confidence == 0.74
    assert any(
        evidence.source == "system_default"
        for evidence in response.profile.time_budget.evidence
    )
    expected = round(
        sum(
            getattr(response.profile, name).confidence
            for name in DevelopmentProfileAgent._profile_field_names()
        )
        / 10,
        3,
    )
    assert response.profile.confidence == expected
    assert len(fake.calls) == 1


def test_llm_profile_updates_previous_version_without_erasing_old_fields() -> None:
    first_fake = FakeLLMClient([_complete_profile_draft()])
    agent = ProfileAgent(first_fake, enable_llm=True)
    first = asyncio.run(agent.extract(_complete_request(), None))

    second_text = "我已经完成Python基础练习，还想掌握模型评估，并且希望用中文学习。"
    empty_scalar = _scalar(None, [], 0.0)
    empty_list = _list([], [], 0.0)
    second_draft = {
        "major": empty_scalar,
        "course": empty_scalar,
        "knowledge_level": empty_scalar,
        "learning_goals": _list(
            ["掌握模型评估"],
            [_evidence("conversation", "想掌握模型评估", "message-b")],
            0.9,
        ),
        "weak_topics": empty_list,
        "learning_history": _list(
            ["完成Python基础练习"],
            [_evidence("conversation", "完成Python基础练习", "message-b")],
            0.9,
        ),
        "cognitive_style": empty_scalar,
        "language_preference": _scalar(
            "中文",
            [_evidence("conversation", "希望用中文学习", "message-b")],
            0.9,
        ),
        "resource_preference": empty_list,
        "time_budget": empty_scalar,
        "next_question": None,
    }
    agent = ProfileAgent(FakeLLMClient([second_draft]), enable_llm=True)
    second_request = ProfileChatRequest(
        student_id=first.profile.student_id,
        conversation_id="conversation-a",
        messages=[ChatMessage(message_id="message-b", role="user", content=second_text)],
    )
    second = asyncio.run(agent.extract(second_request, first.profile))

    assert second.extraction_mode == "llm_structured"
    assert second.profile.version == first.profile.version + 1
    assert second.profile.major.value == "人工智能"
    assert second.profile.weak_topics.value == ["数学基础"]
    assert "掌握模型评估" in second.profile.learning_goals.value
    assert second.profile.language_preference.value == "中文"


def test_llm_profile_missing_dimensions_produce_natural_question() -> None:
    text = "我最近想学习机器学习，但是还不知道应该从哪里开始。"
    draft = {
        "major": _scalar(None),
        "course": _scalar(
            "机器学习",
            [_evidence("conversation", "学习机器学习", "message-incomplete")],
            0.9,
        ),
        "knowledge_level": _scalar(None),
        "learning_goals": _list([], [], 0.0),
        "weak_topics": _list([], [], 0.0),
        "learning_history": _list([], [], 0.0),
        "cognitive_style": _scalar(None),
        "language_preference": _scalar(None),
        "resource_preference": _list([], [], 0.0),
        "time_budget": _scalar(None),
        "next_question": "你之前接触过哪些机器学习概念，或者这是第一次系统学习？",
    }
    request = ProfileChatRequest(
        student_id="incomplete-student",
        messages=[
            ChatMessage(
                message_id="message-incomplete",
                role="user",
                content=text,
            )
        ],
    )
    response = asyncio.run(
        ProfileAgent(FakeLLMClient([draft]), enable_llm=True).extract(request, None)
    )

    assert response.extraction_mode == "llm_structured"
    assert response.is_complete is False
    assert response.missing_dimensions
    assert response.next_question == draft["next_question"]


@pytest.mark.parametrize(
    "fake_response",
    ["{invalid-json", {"major": _scalar("人工智能")}],
)
def test_profile_invalid_json_or_schema_falls_back(fake_response) -> None:
    response = asyncio.run(
        ProfileAgent(
            FakeLLMClient([fake_response]), enable_llm=True
        ).extract(_complete_request(), None)
    )
    assert response.extraction_mode == "development_heuristic"
    assert response.profile.major.value == "人工智能"


def test_profile_timeout_and_missing_client_fall_back() -> None:
    timed_out = asyncio.run(
        ProfileAgent(
            FakeLLMClient([LLMTimeoutError("test timeout")]),
            enable_llm=True,
        ).extract(_complete_request(), None)
    )
    missing_client = asyncio.run(
        ProfileAgent(None, enable_llm=True).extract(_complete_request(), None)
    )
    assert timed_out.extraction_mode == "development_heuristic"
    assert missing_client.extraction_mode == "development_heuristic"


def test_fake_llm_planner_success_is_ordered_and_respects_time_budget() -> None:
    profile = _development_profile()
    fake = FakeLLMClient([_path_draft()])
    path = asyncio.run(
        PlannerAgent(fake, enable_llm=True).generate(profile)
    )

    assert path.generation_mode == "llm_structured"
    assert [step.step for step in path.steps] == [1, 2, 3]
    assert [step.topic for step in path.steps] == [
        "数学基础",
        "支持向量机",
        "Python简单分类项目",
    ]
    assert all(
        step.estimated_minutes <= profile.time_budget.value.minutes_per_day
        for step in path.steps
    )
    assert all(step.recommended_resources for step in path.steps)
    assert all(step.completion_criteria for step in path.steps)


def test_planner_invalid_response_falls_back() -> None:
    profile = _development_profile()
    invalid = _path_draft()
    invalid["steps"][1]["step"] = 3
    path = asyncio.run(
        PlannerAgent(FakeLLMClient([invalid]), enable_llm=True).generate(profile)
    )
    assert path.generation_mode == "development_rule_based"
    assert [step.step for step in path.steps] == list(range(1, len(path.steps) + 1))


def test_openai_compatible_client_rejects_missing_configuration_without_network() -> None:
    with pytest.raises(LLMConfigurationError):
        OpenAICompatibleLLMClient(
            api_key="",
            model="test-model",
            base_url="https://example.invalid/v1",
        )
