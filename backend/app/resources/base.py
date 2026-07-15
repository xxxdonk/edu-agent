from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import uuid4

from app.llm import LLMClient, LLMMessage
from app.orchestrator import SharedAgentContext
from app.rag import KnowledgeRetriever
from app.schemas import Resource, ResourceType, SourceReference
from app.schemas.common import Difficulty

_FALLBACK_REFERENCE = SourceReference(
    source_id="ml-syllabus",
    title="机器学习基础课程大纲",
    locator="data/machine_learning/syllabus.md",
    chunk_id="fallback",
)


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

        rag_chunks = self._retriever.retrieve(topic, difficulty=difficulty)
        references = self._retriever.to_source_references(rag_chunks)
        if not references:
            references = [_FALLBACK_REFERENCE]
        rag_context = self._build_rag_context(rag_chunks)

        if self._enable_llm and self._llm_client is not None:
            return await self._generate_with_llm(context, step, topic, difficulty, rag_context, references)
        return self._generate_heuristic(context, step, topic, difficulty, rag_context, references)

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
        return f"学生薄弱点：{weak_str}；认知风格：{style}；学习目标：{'、'.join(profile.learning_goals.value or ['完成课程'])}"

    @staticmethod
    def _make_resource_id() -> str:
        return str(uuid4())
