from __future__ import annotations

import asyncio
import logging

import pytest

from app.llm import (
    FakeLLMClient,
    LLMConfigurationError,
    LLMTimeoutError,
)
from app.llm.openai_compatible import OpenAICompatibleLLMClient
from app.planner import PlannerAgent
from app.profile import DevelopmentProfileAgent, ProfileAgent
from app.profile.models import ProfileExtractionDraft
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


def _request_with_question_history(
    text: str,
    questions: list[str],
    *,
    student_id: str = "question-history-student",
) -> ProfileChatRequest:
    messages = [
        ChatMessage(message_id="message-a", role="user", content=text),
    ]
    for index, question in enumerate(questions, start=1):
        messages.extend(
            [
                ChatMessage(
                    message_id=f"assistant-{index}",
                    role="assistant",
                    content=question,
                ),
                ChatMessage(
                    message_id=f"user-{index}",
                    role="user",
                    content="我暂时还不确定。",
                ),
            ]
        )
    return ProfileChatRequest(student_id=student_id, messages=messages)


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


def test_profile_question_does_not_target_an_already_identified_field() -> None:
    draft = _complete_profile_draft()
    draft["weak_topics"] = _list([], [], 0.0)
    draft["next_question"] = "你现在主修什么专业？"
    request = _complete_request()
    request.messages[0].content = request.messages[0].content.replace(
        "，数学基础比较一般",
        "",
    )

    response = asyncio.run(
        ProfileAgent(FakeLLMClient([draft]), enable_llm=True).extract(
            request,
            None,
        )
    )

    assert response.missing_dimensions == ["weak_topics"]
    assert response.next_question == "目前哪些概念或题型让你最困惑？"


def test_heuristic_question_repeats_once_then_changes_when_profile_is_unchanged() -> None:
    text = (
        "我是人工智能专业学生，刚开始学习机器学习，希望完成一个分类项目。"
        "我喜欢图示，每天可以学习30分钟。"
    )
    agent = ProfileAgent(None, enable_llm=False)

    first = asyncio.run(agent.extract(_request_with_question_history(text, []), None))
    assert first.next_question is not None
    second = asyncio.run(
        agent.extract(
            _request_with_question_history(text, [first.next_question]),
            first.profile,
        )
    )
    third = asyncio.run(
        agent.extract(
            _request_with_question_history(
                text,
                [first.next_question, second.next_question],
            ),
            second.profile,
        )
    )

    assert second.next_question == first.next_question
    assert third.next_question != first.next_question
    assert third.next_question == "学习过程中，你现在最容易卡在哪个知识点？"


def test_incomplete_profile_never_stops_and_no_question_is_returned_more_than_twice() -> None:
    text = (
        "我是人工智能专业学生，刚开始学习机器学习，希望完成一个分类项目。"
        "我喜欢图示，每天可以学习30分钟。"
    )
    agent = ProfileAgent(None, enable_llm=False)
    previous = None
    questions: list[str] = []

    for _ in range(10):
        response = asyncio.run(
            agent.extract(
                _request_with_question_history(text, questions),
                previous,
            )
        )
        assert response.is_complete is False
        assert response.next_question is not None
        questions.append(response.next_question)
        previous = response.profile

    assert max(questions.count(question) for question in set(questions)) == 2
    assert any("第7次补充" in question for question in questions)


def test_llm_question_repeats_once_then_changes_when_profile_is_unchanged() -> None:
    draft = _complete_profile_draft()
    draft["weak_topics"] = _list([], [], 0.0)
    draft["next_question"] = "目前哪些概念或题型让你最困惑？"
    text = TEST_STUDENT_TEXT.replace("，数学基础比较一般", "")
    agent = ProfileAgent(
        FakeLLMClient([draft, draft, draft]),
        enable_llm=True,
    )

    first = asyncio.run(
        agent.extract(_request_with_question_history(text, []), None)
    )
    assert first.next_question is not None
    second = asyncio.run(
        agent.extract(
            _request_with_question_history(text, [first.next_question]),
            first.profile,
        )
    )
    third = asyncio.run(
        agent.extract(
            _request_with_question_history(
                text,
                [first.next_question, second.next_question],
            ),
            second.profile,
        )
    )

    assert second.next_question == first.next_question
    assert third.next_question != first.next_question


def test_development_profile_extracts_acceptance_case_weak_topics() -> None:
    text = (
        "我是人工智能专业大二学生，目前在学习机器学习，"
        "数学基础一般，梯度下降一直没弄懂，希望完成一个分类项目。"
        "我每天可以学习45分钟，偏好代码案例和图示。"
    )
    request = ProfileChatRequest(
        student_id="acceptance-student",
        messages=[ChatMessage(role="user", content=text)],
    )

    response = DevelopmentProfileAgent().extract(request, None)

    assert response.profile.weak_topics.value == ["数学基础", "梯度下降"]
    assert response.profile.time_budget.value is not None
    assert response.profile.time_budget.value.minutes_per_day == 45
    assert "weak_topics" not in response.missing_dimensions


def test_llm_profile_keeps_explicit_weak_topics_missed_by_model() -> None:
    text = f"{TEST_STUDENT_TEXT}\n梯度下降一直没弄懂。"
    draft = _complete_profile_draft()
    draft["cognitive_style"] = _scalar(None, [], 0.0)
    draft["resource_preference"] = _list(
        ["代码实践案例"],
        [_evidence("inference", "代码案例", "message-a")],
        0.8,
    )
    draft["weak_topics"] = _list(
        ["梯度下降"],
        [_evidence("conversation", "梯度下降一直没弄懂", "message-a")],
        0.9,
    )
    request = ProfileChatRequest(
        student_id="explicit-weak-topics-student",
        messages=[
            ChatMessage(
                message_id="message-a",
                role="user",
                content=text,
            )
        ],
    )

    response = asyncio.run(
        ProfileAgent(FakeLLMClient([draft]), enable_llm=True).extract(request, None)
    )

    assert response.extraction_mode == "llm_structured"
    assert response.profile.weak_topics.value == ["梯度下降", "数学基础"]
    assert response.profile.cognitive_style.value == "visual"
    assert response.profile.resource_preference.value == ["代码实践案例", "思维导图"]
    assert all(
        topic in response.profile.weak_topics.evidence[-1].quote
        for topic in ("梯度下降", "数学基础")
    )


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


def test_profile_timeout_and_missing_client_fall_back(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="app.profile.agent")
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
    assert "profile_fallback reason=structured_extraction_failed" in caplog.text
    assert "profile_fallback reason=llm_client_unavailable" in caplog.text


def test_profile_disabled_reason_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="app.profile.agent")

    response = asyncio.run(
        ProfileAgent(None, enable_llm=False).extract(_complete_request(), None)
    )

    assert response.extraction_mode == "development_heuristic"
    assert "profile_fallback reason=llm_disabled" in caplog.text


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


def test_private_profile_draft_clears_evidence_for_empty_list() -> None:
    raw = _complete_profile_draft()
    raw["weak_topics"] = _list(
        [],
        [_evidence("conversation", "数学基础比较一般")],
        0.9,
    )

    draft = ProfileExtractionDraft.model_validate(raw)

    assert draft.weak_topics.value == []
    assert draft.weak_topics.evidence == []
    assert draft.weak_topics.confidence == 0


def test_private_profile_draft_zeros_confidence_for_null() -> None:
    raw = _complete_profile_draft()
    raw["major"] = _scalar(
        None,
        [_evidence("conversation", "人工智能专业")],
        0.86,
    )

    draft = ProfileExtractionDraft.model_validate(raw)

    assert draft.major.value is None
    assert draft.major.evidence == []
    assert draft.major.confidence == 0


def test_private_profile_draft_treats_empty_string_as_empty_value() -> None:
    raw = _complete_profile_draft()
    raw["major"] = _scalar(
        "  ",
        [_evidence("conversation", "人工智能专业")],
        0.86,
    )
    raw["learning_goals"] = _scalar(
        "",
        [_evidence("conversation", "我想理解支持向量机")],
        0.86,
    )

    draft = ProfileExtractionDraft.model_validate(raw)

    assert draft.major.value is None
    assert draft.learning_goals.value == []
    assert draft.major.evidence == []
    assert draft.learning_goals.evidence == []


def test_private_profile_draft_preserves_nonempty_field() -> None:
    raw = _complete_profile_draft()

    draft = ProfileExtractionDraft.model_validate(raw)

    assert draft.major.value == "人工智能"
    assert draft.major.evidence[0].quote == "人工智能专业"
    assert draft.major.evidence[0].message_id == "message-a"
    assert draft.major.confidence == 0.92


def test_untraceable_field_is_discarded_without_losing_structured_response(
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw = _complete_profile_draft()
    raw["major"] = _scalar(
        "人工智能",
        [_evidence("conversation", "用户从未说过的原文")],
        0.92,
    )
    caplog.set_level(logging.WARNING, logger="app.profile.agent")

    response = asyncio.run(
        ProfileAgent(FakeLLMClient([raw]), enable_llm=True).extract(
            _complete_request(),
            None,
        )
    )

    assert response.extraction_mode == "llm_structured"
    assert response.profile.major.value == "人工智能"
    assert all(
        evidence.quote != "用户从未说过的原文"
        for evidence in response.profile.major.evidence
    )
    assert (
        "profile_field_discarded field=major "
        "reason=conversation_evidence_untraceable"
    ) in caplog.text


def test_untraceable_optional_inference_does_not_downgrade_full_profile() -> None:
    raw = _complete_profile_draft()
    raw["language_preference"] = _scalar(
        "中文",
        [_evidence("inference", "用户没有说过的语言偏好", "message-a")],
        0.7,
    )

    response = asyncio.run(
        ProfileAgent(FakeLLMClient([raw]), enable_llm=True).extract(
            _complete_request(),
            None,
        )
    )

    assert response.extraction_mode == "llm_structured"
    assert response.profile.language_preference.value is None
