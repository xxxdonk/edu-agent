from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from pathlib import Path

import pytest

from app.orchestrator import SharedAgentContext
from app.llm import FakeLLMClient, LLMTimeoutError
from app.planner import DevelopmentPlannerAgent
from app.profile import DevelopmentProfileAgent
from app.rag.loader import load_knowledge_base
from app.rag.retriever import DATA_DIR, KnowledgeRetriever
from app.resources.explanation_agent import ExplanationAgent
from app.schemas import ProfileChatRequest, ResourceGenerationRequest, ResourceType
from app.schemas.profile import ChatMessage


def _context() -> SharedAgentContext:
    request = ProfileChatRequest(
        student_id="rag-test-student",
        messages=[
            ChatMessage(
                role="user",
                content=(
                    "我是人工智能专业学生，刚开始学习机器学习，数学基础比较一般。"
                    "我希望完成一个分类项目，喜欢图示，每天学习30分钟。"
                ),
            )
        ],
    )
    profile = DevelopmentProfileAgent().extract(request, None).profile
    path = DevelopmentPlannerAgent().generate(profile)
    generation_request = ResourceGenerationRequest(
        student_id=profile.student_id,
        path_id=path.path_id,
        step=1,
        resource_types=[ResourceType.EXPLANATION],
    )
    return SharedAgentContext(
        task_id="rag-test-task",
        request=generation_request,
        profile=profile,
        path=path,
    )


def test_knowledge_base_loads_all_eight_chapter_documents() -> None:
    chunks = load_knowledge_base(DATA_DIR)

    chapter_sources = {
        chunk.source_id for chunk in chunks if chunk.source_id.startswith("ml-chapter-")
    }
    assert chapter_sources == {f"ml-chapter-{index:02d}" for index in range(1, 9)}
    assert all("ReservedCode1" not in chunk.content for chunk in chunks)
    assert any("梯度下降" in chunk.content for chunk in chunks)


def test_chinese_learning_description_retrieves_real_chapter_chunks() -> None:
    results = KnowledgeRetriever().retrieve("梯度下降一直没弄懂")

    assert results
    assert results[0][0].source_id == "ml-chapter-02"
    assert "02-线性回归.md" in results[0][0].locator
    assert "梯度下降" in results[0][0].content


def test_unrelated_topic_has_no_fabricated_reference() -> None:
    retriever = KnowledgeRetriever()

    assert retriever.retrieve("量子烹饪星际航海") == []


def test_resource_agent_fails_when_no_reliable_knowledge_source(tmp_path: Path) -> None:
    events: list[dict] = []

    def emit_event(_task_id: str, **payload) -> None:
        events.append(payload)

    agent = ExplanationAgent(
        None,
        KnowledgeRetriever(tmp_path),
        enable_llm=False,
    )
    context = replace(_context(), emit_event=emit_event)

    with pytest.raises(ValueError, match="没有可核验的主题依据"):
        asyncio.run(agent.generate(context))

    assert [event["status"] for event in events] == ["started", "failed"]
    assert all(event["agent"] == "retriever_agent" for event in events)
    assert events[-1]["error"] == "no_reliable_knowledge_source"


def test_resource_agent_emits_real_retrieval_started_and_completed_events() -> None:
    events: list[dict] = []

    def emit_event(_task_id: str, **payload) -> None:
        events.append(payload)

    context = replace(_context(), emit_event=emit_event)
    agent = ExplanationAgent(
        None,
        KnowledgeRetriever(),
        enable_llm=False,
    )

    asyncio.run(agent.generate(context))

    assert [event["status"] for event in events] == ["started", "completed"]
    assert all(event["event_type"] == "agent" for event in events)
    assert all(event["agent"] == "retriever_agent" for event in events)
    assert all(event["resource_type"] == ResourceType.EXPLANATION for event in events)


def test_disabled_resource_generation_is_explicitly_marked_as_fallback() -> None:
    agent = ExplanationAgent(
        None,
        KnowledgeRetriever(),
        enable_llm=False,
    )

    resource = asyncio.run(agent.generate(_context()))

    assert "development fallback" in resource.personalization_reason


def test_llm_failure_safely_falls_back_without_logging_error_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_error_text = "do-not-log-this-provider-response"
    agent = ExplanationAgent(
        FakeLLMClient([LLMTimeoutError(secret_error_text)]),
        KnowledgeRetriever(),
        enable_llm=True,
    )
    caplog.set_level(logging.WARNING, logger="app.resources.base")

    resource = asyncio.run(agent.generate(_context()))

    assert "development fallback" in resource.personalization_reason
    assert "resource_llm_fallback agent=explanation_agent reason=timeout" in caplog.text
    assert secret_error_text not in caplog.text
