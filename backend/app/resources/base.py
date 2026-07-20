from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TypeVar
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from app.llm import (
    LLMClient,
    LLMError,
    LLMMessage,
    LLMResponseFormatError,
    LLMValidationError,
)
from app.orchestrator import SharedAgentContext
from app.rag import KnowledgeRetriever
from app.schemas import Resource, ResourceType, SourceReference
from app.schemas.common import Difficulty
from app.subjects import subject_context_from_profile

logger = logging.getLogger(__name__)

DraftModel = TypeVar("DraftModel", bound=BaseModel)


class ResourceDraftFormatError(ValueError):
    """A safe, model-correctable resource draft format failure."""


class BaseResourceAgent(ABC):
    agent_name: str
    resource_type: ResourceType

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        retriever: KnowledgeRetriever | None = None,
        *,
        enable_llm: bool = False,
    ) -> None:
        self._llm_client = llm_client
        self._retriever = retriever or KnowledgeRetriever()
        self._enable_llm = enable_llm

    async def generate(self, context: SharedAgentContext) -> Resource:
        step = next(
            (s for s in context.path.steps if s.step == context.request.step),
            context.path.steps[0],
        )
        topic = step.topic
        difficulty = context.profile.knowledge_level.value or Difficulty.BEGINNER
        subject = subject_context_from_profile(context.profile)

        self._emit_retrieval_event(
            context,
            status="started",
            progress=10,
            message="Retriever Agent 开始检索课程知识库",
        )
        try:
            rag_chunks = self._retriever.retrieve(
                topic,
                difficulty=difficulty,
                subject_name=subject.subject_name,
                learning_goal=subject.learning_goal,
            )
        except Exception as error:
            self._emit_retrieval_event(
                context,
                status="failed",
                progress=15,
                message="Retriever Agent 检索课程知识库失败",
                error=f"retrieval_error:{type(error).__name__}",
            )
            raise
        references = self._retriever.to_source_references(rag_chunks)
        if not references:
            self._emit_retrieval_event(
                context,
                status="completed",
                progress=15,
                message="本地知识库未命中相关课程资料，将使用通用模型或学科规则生成",
            )
            references = [
                SourceReference(
                    source_id="general-model",
                    title="本地知识库未命中相关课程资料，本资源由通用模型生成",
                    locator="model://general-knowledge",
                    chunk_id=None,
                )
            ]
        else:
            self._emit_retrieval_event(
                context,
                status="completed",
                progress=15,
                message=f"Retriever Agent 完成检索，命中 {len(references)} 个课程片段",
            )
        rag_context = self._build_rag_context(rag_chunks)

        if self._enable_llm and self._llm_client is not None:
            try:
                generated = await self._generate_with_llm(
                    context,
                    step,
                    topic,
                    difficulty,
                    rag_context,
                    references,
                )
                return self._ensure_profile_personalization(generated, context)
            except (LLMError, ValidationError, ResourceDraftFormatError) as error:
                reason = getattr(error, "code", type(error).__name__)
                logger.warning(
                    "resource_llm_fallback agent=%s reason=%s",
                    self.agent_name,
                    reason,
                )
                resource = self._generate_heuristic(
                    context,
                    step,
                    topic,
                    difficulty,
                    rag_context,
                    references,
                )
                return self._mark_development_fallback(resource)
        resource = self._generate_heuristic(
            context,
            step,
            topic,
            difficulty,
            rag_context,
            references,
        )
        return self._mark_development_fallback(resource)

    async def _generate_with_one_format_repair(
        self,
        *,
        system_prompt: str,
        messages: list[LLMMessage],
        response_model: type[DraftModel],
        finalize: Callable[[DraftModel], Resource],
    ) -> Resource:
        """Generate a private draft, allowing exactly one format-only repair.

        Provider/network retries remain the LLM client's responsibility. Safety,
        timeout, network, and server errors intentionally bypass this repair path.
        """

        if self._llm_client is None:
            raise RuntimeError("LLM client is unavailable")

        try:
            draft = await self._llm_client.generate_structured(
                system_prompt=system_prompt,
                messages=messages,
                response_model=response_model,
            )
            resource = finalize(draft)
        except (
            LLMResponseFormatError,
            LLMValidationError,
            ResourceDraftFormatError,
        ) as error:
            reason = getattr(error, "code", type(error).__name__)
            logger.warning(
                "resource_llm_format_repair agent=%s attempt=2 reason=%s",
                self.agent_name,
                reason,
            )
        else:
            logger.info(
                "resource_llm_success agent=%s format_repaired=false",
                self.agent_name,
            )
            return resource

        repair_messages = [
            *messages,
            LLMMessage(
                role="user",
                content=(
                    "上一次响应未通过格式校验。请仅修复输出结构，"
                    "继续严格依据同一知识库内容，不新增来源或无法核验的事实。"
                    "只返回结构化 JSON 对象，不要输出解释或 Markdown 外层代码围栏。"
                ),
            ),
        ]
        repaired_draft = await self._llm_client.generate_structured(
            system_prompt=system_prompt,
            messages=repair_messages,
            response_model=response_model,
        )
        resource = finalize(repaired_draft)
        logger.info(
            "resource_llm_success agent=%s format_repaired=true",
            self.agent_name,
        )
        return resource

    @abstractmethod
    async def _generate_with_llm(
        self,
        context: SharedAgentContext,
        step,
        topic: str,
        difficulty: str,
        rag_context: str,
        references: list[SourceReference],
    ) -> Resource: ...

    @abstractmethod
    def _generate_heuristic(
        self,
        context: SharedAgentContext,
        step,
        topic: str,
        difficulty: str,
        rag_context: str,
        references: list[SourceReference],
    ) -> Resource: ...

    @staticmethod
    def _build_rag_context(chunks: list) -> str:
        if not chunks:
            return ""
        parts: list[str] = []
        for chunk, _score in chunks:
            parts.append(f"## {chunk.title} ({chunk.locator})\n{chunk.content}")
        return "\n\n".join(parts)

    @staticmethod
    def _personalization_reason(context: SharedAgentContext) -> str:
        profile = context.profile
        weak = profile.weak_topics.value or []
        weak_str = "、".join(weak) if weak else "无特定薄弱点"
        style = profile.cognitive_style.value or "综合型"
        course = profile.course.value or "当前学习主题"
        return f"当前课程：{course}；学生薄弱点：{weak_str}；认知风格：{style}；学习目标：{'、'.join(profile.learning_goals.value or ['完成当前学习任务'])}"

    @staticmethod
    def _make_resource_id() -> str:
        return str(uuid4())

    @staticmethod
    def _mark_development_fallback(resource: Resource) -> Resource:
        marker = "development fallback：结构化 LLM 生成不可用，已使用本地规则模板。"
        reason = f"{marker} {resource.personalization_reason}"[:2000]
        return resource.model_copy(update={"personalization_reason": reason})

    @classmethod
    def _ensure_profile_personalization(
        cls,
        resource: Resource,
        context: SharedAgentContext,
    ) -> Resource:
        grounded_reason = cls._personalization_reason(context)
        existing = resource.personalization_reason.strip()
        if grounded_reason in existing:
            return resource
        combined = f"{grounded_reason}；模型补充：{existing}"[:2000]
        return resource.model_copy(update={"personalization_reason": combined})

    def _emit_retrieval_event(
        self,
        context: SharedAgentContext,
        *,
        status: str,
        progress: int,
        message: str,
        error: str | None = None,
    ) -> None:
        if context.emit_event is None:
            return
        context.emit_event(
            context.task_id,
            event_type="agent",
            status=status,
            progress=progress,
            message=message,
            agent="retriever_agent",
            resource_type=self.resource_type,
            error=error,
        )
