from __future__ import annotations

import asyncio
import json
import logging

import pytest

from app.llm import (
    FakeLLMClient,
    LLMNetworkError,
    LLMSafetyRefusalError,
    LLMTimeoutError,
)
from app.orchestrator import SharedAgentContext
from app.planner import DevelopmentPlannerAgent
from app.profile import DevelopmentProfileAgent
from app.rag import KnowledgeRetriever
from app.resources.drafts import MindMapDraft, QuizDraft, ReadingDraft
from app.resources.mindmap_agent import MindMapAgent
from app.resources.quiz_agent import QuizAgent
from app.resources.reading_agent import ReadingAgent
from app.resources.reviewer import ReviewerAgent
from app.schemas import ProfileChatRequest, ResourceGenerationRequest, ResourceType
from app.schemas.profile import ChatMessage


def _context(resource_type: ResourceType) -> SharedAgentContext:
    profile_request = ProfileChatRequest(
        student_id=f"format-test-{resource_type.value}",
        messages=[
            ChatMessage(
                role="user",
                content=(
                    "我是人工智能专业学生，正在学习机器学习，数学基础一般，"
                    "梯度下降没有弄懂，希望完成分类项目，偏好代码案例和图示，"
                    "每天可以学习45分钟。"
                ),
            )
        ],
    )
    profile = DevelopmentProfileAgent().extract(profile_request, None).profile
    path = DevelopmentPlannerAgent().generate(profile)
    request = ResourceGenerationRequest(
        student_id=profile.student_id,
        path_id=path.path_id,
        step=1,
        resource_types=[resource_type],
    )
    return SharedAgentContext(
        task_id=f"format-task-{resource_type.value}",
        request=request,
        profile=profile,
        path=path,
    )


def _valid_quiz() -> dict:
    return {
        "basic": {
            "question": "梯度下降每次更新参数时通常沿哪个方向移动？",
            "options": [
                "负梯度方向",
                "正梯度方向",
                "随机标签方向",
                "固定参数方向",
            ],
            "answer": "a.",
            "explanation": "负梯度方向对应目标函数在局部下降最快的方向。",
        },
        "intermediate": {
            "question": "学习率过大或过小时分别可能出现什么现象？",
            "answer": "过大可能震荡或发散，过小会使收敛速度变慢。",
            "explanation": "学习率控制每一步参数更新的幅度。",
        },
        "challenge": {
            "question": "如何在分类项目中判断梯度下降是否正常收敛？",
            "answer": "记录训练与验证损失，观察趋势并结合学习率检查震荡和停滞。",
            "explanation": "同时观察训练和验证指标可以区分优化与泛化问题。",
        },
    }


def _valid_mind_map() -> dict:
    return {
        "content": (
            "\ufeff```mermaid\r\n"
            "MindMap\r\n"
            "  root((梯度下降))\r\n"
            "    目标函数\r\n"
            "      最小化损失\r\n"
            "    参数更新\r\n"
            "      负梯度方向\r\n"
            "    学习率\r\n"
            "      控制更新步长\r\n"
            "```"
        )
    }


def _valid_reading() -> dict:
    return {
        "overview": "梯度下降通过迭代更新参数来减小目标函数。\n理解它需要联系导数与优化目标。",
        "core_points": [
            "- 梯度表示目标函数在当前位置变化最快的方向。",
            "学习率决定每次参数更新的步长。",
            "训练损失与验证损失应结合观察。",
        ],
        "practice_connection": "在分类项目中记录每轮损失，并比较不同学习率的收敛曲线。",
        "further_study": "继续学习随机梯度下降、动量方法以及模型评估。",
    }


def test_quiz_private_draft_is_fixed_and_binds_local_question_ids() -> None:
    fake = FakeLLMClient([_valid_quiz()])
    context = _context(ResourceType.QUIZ)
    resource = asyncio.run(
        QuizAgent(fake, KnowledgeRetriever(), enable_llm=True).generate(context)
    )

    assert len(fake.calls) == 1
    assert fake.calls[0]["response_model"] is QuizDraft
    assert "development fallback" not in resource.personalization_reason
    payload = json.loads(resource.content)
    questions = payload["questions"]
    assert len(questions) == 3
    assert [question["type"] for question in questions] == [
        "single_choice",
        "short_answer",
        "comprehensive",
    ]
    assert [question["level"] for question in questions] == [
        "basic",
        "intermediate",
        "advanced",
    ]
    assert all(
        question["id"] == f"{resource.resource_id}::q{index}"
        for index, question in enumerate(questions, start=1)
    )
    assert questions[0]["options"] == [
        "A. 负梯度方向",
        "B. 正梯度方向",
        "C. 随机标签方向",
        "D. 固定参数方向",
    ]
    assert questions[0]["answer"] == "A"
    assert asyncio.run(ReviewerAgent().review(resource, context)).review_status == "approved"


def test_quiz_normalizes_exact_three_question_list_and_explicit_answer_text() -> None:
    draft = QuizDraft.model_validate(
        {
            "topic": "梯度下降",
            "difficulty": "beginner",
            "questions": [
                {
                    "id": "model-generated-id",
                    "type": "single_choice",
                    "level": "basic",
                    "question": "参数应沿哪个方向更新？",
                    "options": [
                        {"label": "A", "text": "负梯度方向"},
                        {"label": "B", "text": "正梯度方向"},
                        {"label": "C", "text": "固定方向"},
                        {"label": "D", "text": "随机标签方向"},
                    ],
                    "answer": "A. 负梯度方向",
                    "explanation": "负梯度方向使目标函数在局部下降最快。",
                },
                {
                    "type": "short_answer",
                    "level": "intermediate",
                    "question": "学习率控制什么？",
                    "options": [],
                    "answer": "控制参数更新步长。",
                    "explanation": "过大可能震荡，过小会收敛缓慢。",
                },
                {
                    "type": "comprehensive",
                    "level": "advanced",
                    "question": "如何检查收敛？",
                    "options": [],
                    "answer": "比较训练和验证损失曲线。",
                    "explanation": "损失趋势能帮助区分优化和泛化问题。",
                },
            ],
        }
    )

    assert draft.basic.answer == "A"
    assert draft.basic.options[0] == "A. 负梯度方向"
    assert draft.intermediate.answer == "控制参数更新步长。"
    assert draft.challenge.answer == "比较训练和验证损失曲线。"


def test_quiz_does_not_infer_an_ambiguous_choice_answer() -> None:
    invalid = _valid_quiz()
    invalid["basic"]["answer"] = "负梯度可能是答案，也可能不是"

    with pytest.raises(ValueError):
        QuizDraft.model_validate(invalid)


def test_mind_map_private_draft_normalizes_only_safe_format_noise() -> None:
    fake = FakeLLMClient([_valid_mind_map()])
    context = _context(ResourceType.MIND_MAP)
    resource = asyncio.run(
        MindMapAgent(fake, KnowledgeRetriever(), enable_llm=True).generate(context)
    )

    assert len(fake.calls) == 1
    assert fake.calls[0]["response_model"] is MindMapDraft
    assert resource.content.startswith("mindmap\n")
    assert "```" not in resource.content
    assert "\r" not in resource.content
    assert asyncio.run(ReviewerAgent().review(resource, context)).review_status == "approved"


def test_reading_private_draft_renders_fixed_simple_markdown_sections() -> None:
    fake = FakeLLMClient([_valid_reading()])
    context = _context(ResourceType.READING)
    resource = asyncio.run(
        ReadingAgent(fake, KnowledgeRetriever(), enable_llm=True).generate(context)
    )

    assert len(fake.calls) == 1
    assert fake.calls[0]["response_model"] is ReadingDraft
    assert resource.content.count("\n- ") == 3
    assert "## 概览" in resource.content
    assert "## 三个核心要点" in resource.content
    assert "## 实践联系" in resource.content
    assert "## 后续学习" in resource.content
    assert "- - " not in resource.content
    assert asyncio.run(ReviewerAgent().review(resource, context)).review_status == "approved"


@pytest.mark.parametrize(
    ("agent_class", "resource_type", "invalid", "valid"),
    [
        (QuizAgent, ResourceType.QUIZ, {"basic": {}}, _valid_quiz()),
        (
            MindMapAgent,
            ResourceType.MIND_MAP,
            {"content": "graph TD\n  A --> B"},
            _valid_mind_map(),
        ),
        (
            ReadingAgent,
            ResourceType.READING,
            {
                "overview": "概览",
                "core_points": ["要点一", "要点二"],
                "practice_connection": "实践",
                "further_study": "后续",
            },
            _valid_reading(),
        ),
    ],
)
def test_one_invalid_format_gets_exactly_one_repair_request(
    agent_class,
    resource_type: ResourceType,
    invalid: dict,
    valid: dict,
) -> None:
    fake = FakeLLMClient([invalid, valid])
    resource = asyncio.run(
        agent_class(fake, KnowledgeRetriever(), enable_llm=True).generate(
            _context(resource_type)
        )
    )

    assert len(fake.calls) == 2
    assert "上一次响应未通过格式校验" in fake.calls[1]["messages"][-1].content
    assert "development fallback" not in resource.personalization_reason


@pytest.mark.parametrize(
    ("agent_class", "resource_type", "invalid"),
    [
        (QuizAgent, ResourceType.QUIZ, {"basic": {}}),
        (MindMapAgent, ResourceType.MIND_MAP, {"content": "graph TD\n  A --> B"}),
        (
            ReadingAgent,
            ResourceType.READING,
            {
                "overview": "概览",
                "core_points": ["只有一个"],
                "practice_connection": "实践",
                "further_study": "后续",
            },
        ),
    ],
)
def test_second_invalid_format_uses_explicit_fallback(
    agent_class,
    resource_type: ResourceType,
    invalid: dict,
) -> None:
    fake = FakeLLMClient([invalid, invalid])
    resource = asyncio.run(
        agent_class(fake, KnowledgeRetriever(), enable_llm=True).generate(
            _context(resource_type)
        )
    )

    assert len(fake.calls) == 2
    assert "development fallback" in resource.personalization_reason


@pytest.mark.parametrize(
    "error",
    [
        LLMSafetyRefusalError("safe-test-refusal"),
        LLMTimeoutError("safe-test-timeout"),
        LLMNetworkError("safe-test-network"),
    ],
)
def test_non_format_errors_do_not_trigger_format_repair(error: Exception) -> None:
    fake = FakeLLMClient([error])
    resource = asyncio.run(
        QuizAgent(fake, KnowledgeRetriever(), enable_llm=True).generate(
            _context(ResourceType.QUIZ)
        )
    )

    assert len(fake.calls) == 1
    assert "development fallback" in resource.personalization_reason


def test_format_logs_never_include_invalid_model_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_content = "do-not-log-private-model-output"
    fake = FakeLLMClient([secret_content, secret_content])
    caplog.set_level(logging.INFO, logger="app.resources.base")

    resource = asyncio.run(
        MindMapAgent(fake, KnowledgeRetriever(), enable_llm=True).generate(
            _context(ResourceType.MIND_MAP)
        )
    )

    assert len(fake.calls) == 2
    assert "development fallback" in resource.personalization_reason
    assert "resource_llm_format_repair" in caplog.text
    assert "resource_llm_fallback" in caplog.text
    assert secret_content not in caplog.text
